from pathlib import Path
import pandas as pd
import hashlib
import re

DEBUG_DIR = Path("data/outputs/debug")
OUT_DIR = Path("data/outputs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Heuristik: region + land + språk ----------------------------------------

def infer_region(broadcast: str | None, place: str | None, lang: str | None) -> str:
    s = f"{broadcast or ''} {place or ''} {lang or ''}".lower()
    if "pal" in s:
        return "PAL"
    if "ntsc-j" in s or "jpn" in s or "japan" in s:
        return "NTSC-J"
    if "ntsc" in s or "usa" in s or "united states" in s or "u.s." in s:
        return "NTSC-U"
    # fallback via språk
    if "japanese" in s or "日本語" in s:
        return "NTSC-J"
    if "english" in s:
        return "NTSC-U"
    return "UNKNOWN"

COUNTRY_HINTS = {
    # Nordics
    "sweden": "SE", "svenska": "SE", "sverige": "SE",
    "norway": "NO", "norge": "NO", "norwegian": "NO",
    "denmark": "DK", "danmark": "DK", "danish": "DK",
    "finland": "FI", "finnish": "FI", "suomi": "FI", "suomen": "FI",
    "iceland": "IS",

    # DACH
    "germany": "DE", "deutschland": "DE", "german": "DE",
    "austria": "AT", "österreich": "AT",
    "switzerland": "CH", "schweiz": "CH", "suisse": "CH", "svizzera": "CH",

    # Benelux
    "belgium": "BE", "belgië": "BE", "belgique": "BE",
    "netherlands": "NL", "the netherlands": "NL", "holland": "NL", "nederland": "NL",
    "luxembourg": "LU", "letzebuerg": "LU", "luxemburg": "LU",

    # Western Europe
    "france": "FR", "français": "FR",
    "spain": "ES", "españa": "ES",
    "portugal": "PT", "português": "PT",
    "italy": "IT", "italia": "IT",
    "ireland": "IE", "eire": "IE",
    "united kingdom": "GB", "uk": "GB", "england": "GB", "scotland": "GB", "wales": "GB",

    # Central/Eastern Europe
    "poland": "PL", "polska": "PL",
    "czechia": "CZ", "czech republic": "CZ", "česko": "CZ",
    "slovakia": "SK", "slovensko": "SK",
    "hungary": "HU", "magyarország": "HU",
    "romania": "RO", "bulgaria": "BG", "croatia": "HR", "slovenia": "SI",
    "greece": "GR", "hellas": "GR",
    "lithuania": "LT", "latvia": "LV", "estonia": "EE",

    # Americas
    "usa": "US", "united states": "US", "u.s.": "US", "america": "US",
    "canada": "CA",
    "mexico": "MX",
    "brazil": "BR", "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE",

    # Asia
    "japan": "JP", "nippon": "JP", "nihon": "JP",
    "china": "CN", "prc": "CN",
    "taiwan": "TW",
    "korea": "KR", "south korea": "KR", "republic of korea": "KR",
    "hong kong": "HK", "singapore": "SG",
    "india": "IN",
    "thailand": "TH", "malaysia": "MY",
    "philippines": "PH", "indonesia": "ID",
    "vietnam": "VN",

    # Oceania
    "australia": "AU", "new zealand": "NZ",

    # Middle East & Africa (vanliga)
    "israel": "IL", "turkey": "TR", "saudi arabia": "SA", "uae": "AE", "united arab emirates": "AE",
    "egypt": "EG", "south africa": "ZA",

    # Special
    "worldwide": "WW", "global": "WW", "international": "WW", "europe": "EU", "scandinavia": "SCAND",
}

LANG_HINTS = {
    # stora språk + autonymer
    "english": "en", "eng": "en",
    "svenska": "sv", "swedish": "sv",
    "norsk": "no", "norwegian": "no", "bokmål": "nb", "nynorsk": "nn",
    "dansk": "da", "danish": "da",
    "suomi": "fi", "finnish": "fi",
    "deutsch": "de", "german": "de",
    "français": "fr", "french": "fr",
    "español": "es", "spanish": "es", "castellano": "es",
    "português": "pt", "portuguese": "pt",
    "italiano": "it", "italian": "it",
    "nederlands": "nl", "dutch": "nl",
    "polski": "pl", "polish": "pl",
    "čeština": "cs", "czech": "cs",
    "magyar": "hu", "hungarian": "hu",
    "ελληνικά": "el", "greek": "el",
    "русский": "ru", "russian": "ru",
    "日本語": "ja", "japanese": "ja",
    "한국어": "ko", "korean": "ko",
    "中文": "zh", "chinese": "zh", "简体中文": "zh-Hans", "繁體中文": "zh-Hant",
}

# ---- Hjälpare ----
def _to_str(x):
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)

def _lower(x):
    try:
        s = _to_str(x)
        return s.lower()
    except Exception:
        return ""

# ISO2 & flagg-emojis
ISO2_RE = re.compile(r"\b([A-Z]{2})\b")
FLAG_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")

def _flag_to_iso2(flag: str) -> str | None:
    if not flag or len(flag) != 2:
        return None
    base = ord("\U0001F1E6")
    return "".join(chr(ord(c) - base + ord('A')) for c in flag)

def split_multi(val: str | None):
    s = _to_str(val).replace("|", ";").replace(",", ";")
    return [p.strip() for p in s.split(";") if p.strip()]

def guess_countries(place: str | None, broadcast: str | None = "", title: str | None = "") -> list[str]:
    place_s = _to_str(place)
    bcast_s = _to_str(broadcast)
    title_s = _to_str(title)

    full_low = _lower(" | ".join([place_s, title_s, bcast_s]))
    found = set()

    # 1) Emoji-flaggor
    for m in FLAG_RE.finditer(place_s + " " + title_s + " " + bcast_s):
        iso = _flag_to_iso2(m.group())
        if iso:
            found.add(iso)

    # 2) Ordbok/autonymer
    for k, code in COUNTRY_HINTS.items():
        if k in full_low:
            found.add(code)

    # 3) ISO2 i place_of_publication (med blocklista mot brus)
    BLOCK = {"II", "IV", "VI", "SN", "ES", "NE", "PS", "CD", "FX", "TV", "GP", "SD"}
    for m in ISO2_RE.finditer(place_s):
        iso = m.group(1)
        if iso not in BLOCK:
            found.add(iso)

    # 4) Region-hint → land/region
    if not found:
        b = _lower(bcast_s)
        if "ntsc-j" in b or "jpn" in b or "japan" in full_low:
            found.add("JP")
        elif "ntsc" in b or "usa" in full_low or "united states" in full_low or "u.s." in full_low:
            found.add("US")
        elif "pal" in b or "europe" in full_low or "eu" in full_low:
            found.add("EU")

    # 5) Sista fallback: UNK (inte WW)
    if not found:
        found.add("UNK")

    return sorted(found)

def guess_languages(lang_field: str | None, title: str | None = "", place: str | None = "") -> list[str]:
    langs = set()

    # 1) explicit lista i fältet
    for token in split_multi(lang_field):
        t = _lower(token)
        if t in LANG_HINTS:
            langs.add(LANG_HINTS[t])
        else:
            for k, code in LANG_HINTS.items():
                if re.search(rf"\b{k}\b", t):
                    langs.add(code)

    # 2) leta även i titel/plats
    for blob in (title, place):
        t = _lower(blob)
        for k, code in LANG_HINTS.items():
            if k in t:
                langs.add(code)

    # 3) skript-hint
    t_all = f"{_to_str(lang_field)} {_to_str(title)} {_to_str(place)}"
    if "日本語" in t_all:
        langs.add("ja")

    # 4) sista fallback: xx (okänt)
    if not langs:
        langs.add("xx")

    return sorted(langs)

# --- ID-hjälpare --------------------------------------------------------------

def edition_key(title: str, platform: str, region: str) -> str:
    return f"{title.strip()}|{platform.strip()}|{region.strip()}"

def edition_id_from_key(key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10].upper()
    return f"ED-{h}"

def release_key(edition_id: str, country: str, language: str, date: str) -> str:
    return f"{edition_id}|{country}|{language}|{date}"

def release_id_from_key(key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10].upper()
    return f"RL-{h}"

# --- Huvud --------------------------------------------------------------------

def main():
    files = sorted(DEBUG_DIR.glob("_debug_normalized_*.csv"))
    if not files:
        print("❌ Hittade inga debug-filer i data/outputs/debug/. Kör normalize först.")
        return

    dfs = [pd.read_csv(p, dtype=str).fillna("") for p in files]
    data = pd.concat(dfs, ignore_index=True)

    # Bara spel (inte accessories)
    games = data[(data.get("accessory_type", "") == "")].copy()

    # Region (grov) per rad (används i edition_key)
    games.loc[:, "region"] = games.apply(
        lambda r: infer_region(r.get("broadcast_standard"), r.get("place_of_publication"), r.get("title.language")),
        axis=1
    )

    releases_rows = []
    items_rows = []
    expanded_rows = []  # objects_expanded.csv

    for _, r in games.iterrows():
        platform = r.get("platform_norm", "")
        region = r.get("region", "")
        parent_obj = r.get("object_number", "")

        # --- Bundle-detektion ---
        cat = _lower(r.get("object_category"))
        ttype = _lower(r.get("title.type"))
        ontype = _lower(r.get("object_name.type"))
        is_bundle = any(x in cat for x in ["bundle", "compilation", "collection"]) \
                    or "bundle" in ttype or "bundle" in ontype

        # Titlar att emittera
        if is_bundle:
            alt = [t for t in _to_str(r.get("alt_titles")).split("|") if t.strip()]
            titles_to_emit = alt if alt else [_to_str(r.get("title_primary"))]
        else:
            titles_to_emit = [_to_str(r.get("title_primary"))]

        # Länder & språk
        countries = guess_countries(
            r.get("place_of_publication"),
            r.get("broadcast_standard"),
            r.get("title")
        )
        langs = guess_languages(
            r.get("title.language"),
            r.get("title_primary"),
            r.get("place_of_publication")
        )

        # --- objects_expanded: parent alltid med ---
        expanded_rows.append({
            "object_id": parent_obj,
            "parent_object": "",
            "source_object": parent_obj,
            "title_primary": _to_str(r.get("title_primary")),
            "platform_norm": platform,
            "object_category": _to_str(r.get("object_category")),
            "is_virtual_child": False,
        })

        # --- Emission per titel ---
        if is_bundle:
            # Skapa stabila child-ids parent#1, #2, ...
            for idx, t in enumerate(titles_to_emit, start=1):
                child_id = f"{parent_obj}#{idx}"

                # Virtuellt barn-objekt
                expanded_rows.append({
                    "object_id": child_id,
                    "parent_object": parent_obj,
                    "source_object": parent_obj,
                    "title_primary": t,
                    "platform_norm": platform,
                    "object_category": "bundle-child",
                    "is_virtual_child": True,
                })

                ed_key = edition_key(t, platform, region)
                ed_id  = edition_id_from_key(ed_key)

                items_rows.append({
                    "object_number": child_id,  # mappa barnet till editionen
                    "edition_id": ed_id
                })

                for c in countries:
                    for l in langs:
                        releases_rows.append({
                            "edition_id": ed_id,
                            "title_primary": t,
                            "platform": platform,
                            "country": c,
                            "language": l,
                            "release_date": "",
                            "source_object": child_id,
                        })
        else:
            # Icke-bundle → mappa originalobjektet som vanligt
            t = titles_to_emit[0]
            ed_key = edition_key(t, platform, region)
            ed_id  = edition_id_from_key(ed_key)

            items_rows.append({
                "object_number": parent_obj,
                "edition_id": ed_id
            })

            for c in countries:
                for l in langs:
                    releases_rows.append({
                        "edition_id": ed_id,
                        "title_primary": t,
                        "platform": platform,
                        "country": c,
                        "language": l,
                        "release_date": "",
                        "source_object": parent_obj,
                    })

    # --- Normalisera releases till unik nivå + separata källor -----------------
    releases_raw = pd.DataFrame(releases_rows)

    if releases_raw.empty:
        print("❌ Inga releases genererades.")
        return

    keycols = ["edition_id", "country", "language", "release_date"]
    releases_raw["release_key"] = releases_raw.apply(
        lambda r: release_key(r["edition_id"], r["country"], r["language"], r["release_date"]),
        axis=1
    )
    releases_raw["release_id"] = releases_raw["release_key"].apply(release_id_from_key)

    # release_sources: en rad per (release_id, source_object)
    release_sources = (
        releases_raw.loc[:, ["release_id", "source_object"]]
        .drop_duplicates()
        .sort_values(["release_id", "source_object"])
    )

    # releases (unika): droppa dubbletter på nyckeln, ta representativ titel/plattform
    releases = (
        releases_raw
        .sort_values(["edition_id", "title_primary", "platform"])  # determinism
        .drop_duplicates(subset=["release_key"])
        .loc[:, ["release_id", "edition_id", "title_primary", "platform", "country", "language", "release_date"]]
        .sort_values(["title_primary", "platform", "country", "language"])
    )

    # --- Skriv ut releases & release_sources ----------------------------------
    releases.to_csv(OUT_DIR / "releases.csv", index=False, encoding="utf-8")
    release_sources.to_csv(OUT_DIR / "release_sources.csv", index=False, encoding="utf-8")

    # --- items_to_editions -----------------------------------------------------
    items_to_editions = pd.DataFrame(items_rows).drop_duplicates()
    items_to_editions.to_csv(OUT_DIR / "items_to_editions.csv", index=False, encoding="utf-8")

    # --- objects_expanded ------------------------------------------------------
    objects_expanded = pd.DataFrame(expanded_rows).drop_duplicates()
    objects_expanded.to_csv(OUT_DIR / "objects_expanded.csv", index=False, encoding="utf-8")

    # --- editions: EN rad per edition_id --------------------------------------
    editions = (
        releases.loc[:, ["edition_id", "title_primary", "platform"]]
                .drop_duplicates(subset=["edition_id"])
                .sort_values(["title_primary", "platform"])
    )

    # region-map (deterministiskt från games)
    region_map = (
        games.assign(_edkey = games.apply(lambda r: edition_key(r.get("title_primary",""), r.get("platform_norm",""), r.get("region","")), axis=1))
             .assign(_edid  = lambda df: df["_edkey"].apply(edition_id_from_key))
             .loc[:, ["_edid", "region"]]
             .drop_duplicates(subset=["_edid"])
             .rename(columns={"_edid":"edition_id"})
    )
    editions = editions.merge(region_map, on="edition_id", how="left").fillna({"region": ""})
    editions.to_csv(OUT_DIR / "editions.csv", index=False, encoding="utf-8")

    # --- Snabb summering -------------------------------------------------------
    print(f"✅ releases.csv: {len(releases)} rader (unika)")
    print(f"✅ release_sources.csv: {len(release_sources)} kopplingar release↔source_object")
    print(f"✅ editions.csv: {len(editions)} editioner (unika)")
    print(f"✅ items_to_editions.csv: {len(items_to_editions)} kopplingar")
    print(f"✅ objects_expanded.csv: {len(objects_expanded)} objekt (inkl. virtuella barn)")

    rel_by_country = releases["country"].value_counts().head(15)
    rel_by_lang = releases["language"].value_counts().head(15)

    print("\nReleases per country (top 15):")
    print(rel_by_country.to_string())
    print("\nReleases per language (top 15):")
    print(rel_by_lang.to_string())

    # Liten bundle-rapport
    child_counts = (
        objects_expanded[objects_expanded["is_virtual_child"] == True]
        .groupby("parent_object")["object_id"]
        .count()
        .sort_values(ascending=False)
        .head(10)
    )
    if not child_counts.empty:
        print("\nBundle parents (top 10 by child count):")
        print(child_counts.to_string())

    print("\nExempel releases:")
    print(releases.head(10).to_string(index=False))

if __name__ == "__main__":
    main()
