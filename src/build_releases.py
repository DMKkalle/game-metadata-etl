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

# Fångar ISO2 (SE, US) och flagg-emojis (🇸🇪)
ISO2_RE = re.compile(r"\b([A-Z]{2})\b")
FLAG_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")

def _flag_to_iso2(flag: str) -> str | None:
    if not flag or len(flag) != 2:
        return None
    base = ord("\U0001F1E6")
    return "".join(chr(ord(c) - base + ord('A')) for c in flag)

def split_multi(val: str | None):
    s = _to_str(val).replace("|", ";").replace(",", ";")
    parts = [p.strip() for p in s.split(";") if p.strip()]
    return parts

def guess_countries(place: str | None, broadcast: str | None = "", title: str | None = "") -> list[str]:
    # Coerce till str
    place_s = _to_str(place)
    bcast_s = _to_str(broadcast)
    title_s = _to_str(title)

    # Vi tittar på HINTS i HELA texten...
    full_low = _lower(" | ".join([place_s, title_s, bcast_s]))
    found = set()

    # 1) Emoji-flaggor i hela texten
    for m in FLAG_RE.finditer(place_s + " " + title_s + " " + bcast_s):
        iso = _flag_to_iso2(m.group())
        if iso:
            found.add(iso)

    # 2) Ordbok/autonymer i hela texten
    for k, code in COUNTRY_HINTS.items():
        if k in full_low:
            found.add(code)

    # 3) ISO2-koder BARA i 'place' (inte i titel/broadcast), och med hård blocklist
    BLOCK = {"II", "IV", "VI", "SN", "ES", "NE", "PS", "CD", "FX", "TV", "GP", "SD"}  # filtrera bort brus
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

    # 5) Sista fallback
    if not found:
        found.add("WW")

    return sorted(found)


def guess_languages(lang_field: str | None, title: str | None = "", place: str | None = "") -> list[str]:
    # Coerce to strings up front
    lang_s = _to_str(lang_field)
    title_s = _to_str(title)
    place_s = _to_str(place)

    langs = set()

    # 1) explicit lista i fältet
    for token in split_multi(lang_s):
        t = _lower(token)
        if t in LANG_HINTS:
            langs.add(LANG_HINTS[t])
        else:
            for k, code in LANG_HINTS.items():
                if re.search(rf"\b{k}\b", t):
                    langs.add(code)

    # 2) leta även i titel/plats
    for blob in (title_s, place_s):
        t = _lower(blob)
        for k, code in LANG_HINTS.items():
            if k in t:
                langs.add(code)

    # 3) skript-hint
    t_all = f"{lang_s} {title_s} {place_s}"
    if "日本語" in t_all:
        langs.add("ja")

    # 4) sista fallback
    if not langs:
        langs.add("xx")

    return sorted(langs)


# --- Edition-id från (title_primary, platform, region) ------------------------

def edition_key(title: str, platform: str, region: str) -> str:
    return f"{title.strip()}|{platform.strip()}|{region.strip()}"

def edition_id_from_key(key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10].upper()
    return f"ED-{h}"

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

    # Region (grov) för stabil edition_id
    games.loc[:, "region"] = games.apply(
        lambda r: infer_region(r.get("broadcast_standard"), r.get("place_of_publication"), r.get("title.language")),
        axis=1
    )

    games.loc[:, "edition_key"] = games.apply(
        lambda r: edition_key(r.get("title_primary", ""), r.get("platform_norm", ""), r.get("region", "")),
        axis=1
    )
    games.loc[:, "edition_id"] = games["edition_key"].apply(edition_id_from_key)

    # ---- Bygg releases: Edition + Land + Språk ----
    rows = []
    for _, r in games.iterrows():
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

        for c in countries:
            for l in langs:
                rows.append({
                    "edition_id": r["edition_id"],
                    "title_primary": r.get("title_primary", ""),
                    "platform": r.get("platform_norm", ""),
                    "country": c,          # ISO-liknande kod, EU/WW som special
                    "language": l,         # ISO-liknande kod, xx = okänt
                    "release_date": "",    # (valfritt; fylls om ni har datum)
                    "source_object": r.get("object_number", ""),
                })

    releases = pd.DataFrame(rows).drop_duplicates().sort_values(
        ["title_primary", "platform", "country", "language"]
    )
    releases.to_csv(OUT_DIR / "releases.csv", index=False, encoding="utf-8")

    # editions (unika)
    editions = (
        games.rename(columns={"platform_norm": "platform"})
             .loc[:, ["edition_id", "title_primary", "platform", "region"]]
             .drop_duplicates()
             .sort_values(["title_primary", "platform", "region"])
    )
    editions.to_csv(OUT_DIR / "editions.csv", index=False, encoding="utf-8")

    # objekt → edition
    items_to_editions = games.loc[:, ["object_number", "edition_id"]].drop_duplicates()
    items_to_editions.to_csv(OUT_DIR / "items_to_editions.csv", index=False, encoding="utf-8")

    # --- Snabb summering ---
    print(f"✅ releases.csv: {len(releases)} rader")
    print(f"✅ editions.csv: {len(editions)} editioner")
    print(f"✅ items_to_editions.csv: {len(items_to_editions)} kopplingar")

    rel_by_country = releases["country"].value_counts().head(15)
    rel_by_lang = releases["language"].value_counts().head(15)

    print("\nReleases per country (top 15):")
    print(rel_by_country.to_string())

    print("\nReleases per language (top 15):")
    print(rel_by_lang.to_string())

    print("\nExempel releases:")
    print(releases.head(10).to_string(index=False))

if __name__ == "__main__":
    main()
