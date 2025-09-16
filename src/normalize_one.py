"""
normalize_one.py — Steg 2: Normalisera EN rå-CSV (förhandsvisning)

Syfte:
- Läsa första CSV i data/raw/
- Normalisera plattform -> 'platform_norm' (SNES/SFC/…)
- Dela titel -> 'title_primary' + 'alt_titles'
- Klassificera tillbehör -> 'accessory_type' (manual/soundtrack/poster/…)
- INTE ändra originalet. Skriv bara en debug-fil till data/outputs/_debug_normalized.csv

Körning:
    python src/normalize_one.py

Krav:
- pandas, pyyaml
- configs/platform_map.yaml        (valfritt men rekommenderas)
- configs/accessory_map.yaml       (valfritt men rekommenderas)
"""

from pathlib import Path
import re
import pandas as pd
import yaml

# --- Paths --------------------------------------------------------------------
RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/outputs")
PLATFORM_MAP_PATH = Path("configs/platform_map.yaml")
ACCESSORY_MAP_PATH = Path("configs/accessory_map.yaml")

# --- Hjälpare: robust CSV-läsning --------------------------------------------
def read_csv_auto(p: Path, encodings=("utf-8", "latin1", "utf-16"), seps=(",", ";", "\t")):
    """
    Testa flera encodings och separatorer tills något funkar.
    Om allt landar i 1 kolumn (troligen fel sep) -> prova nästa.
    """
    for enc in encodings:
        for sep in seps:
            try:
                df = pd.read_csv(p, encoding=enc, sep=sep)
                if df.shape[1] == 1 and sep != "\t":
                    continue
                return df, enc, sep
            except Exception:
                continue
    raise RuntimeError(f"Kunde inte läsa: {p} med vanliga encodings/separatorer")

# --- Plattform-normalisering --------------------------------------------------
def load_platform_map():
    """
    Ladda configs/platform_map.yaml om den finns.
    Om den saknas: returnera en minimal fallback-karta.
    """
    if PLATFORM_MAP_PATH.exists():
        with open(PLATFORM_MAP_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    # Minimal fallback så skriptet alltid fungerar
    return {
        "exact_map": {
            "Nintendo Super Famicom": "SFC",
            "Super Famicom": "SFC",
            "SFC": "SFC",
            "Nintendo Super Nintendo Entertainment System": "SNES",
            "Super Nintendo": "SNES",
            "Super NES": "SNES",
            "SNES": "SNES",
        },
        "alias_map": {
            "SNES": ["Nintendo Super NES", "SNS"],
            "SFC":  ["SHVC"],
        },
        "regex_map": [
            {"pattern": r"(?i)^snes(\b|[^a-z])|super\s*nintendo", "code": "SNES"},
            {"pattern": r"(?i)^sfc(\b|[^a-z])|super\s*famicom|\bshvc\b", "code": "SFC"},
        ]
    }

def canon_platform(raw_value: str, pmap: dict) -> str | None:
    """
    Gör om ett rått plattformsnamn till en kanonisk kod (SNES/SFC/…).
    - exact_map -> alias_map -> regex_map
    - Returnerar None om inget känns igen (vi flaggar det som okänt senare).
    """
    if raw_value is None:
        return None
    raw = str(raw_value).strip()
    if not raw:
        return None

    ex = (pmap.get("exact_map") or {})
    if raw in ex:
        return ex[raw]

    alias = (pmap.get("alias_map") or {})
    for code, arr in alias.items():
        if any(raw == a for a in arr):
            return code

    for spec in (pmap.get("regex_map") or []):
        if re.search(spec["pattern"], raw):
            return spec["code"]

    return None  # okänd plattform

# --- Accessory-normalisering --------------------------------------------------
def load_accessory_map():
    """
    Ladda configs/accessory_map.yaml om den finns.
    Struktur förväntas:
      exact_map: { "Manual": "manual", "Vinyl": "soundtrack", ... }
      regex_map: [ {pattern: "...", code: "manual"}, ... ]
    """
    if ACCESSORY_MAP_PATH.exists():
        with open(ACCESSORY_MAP_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # fallback if keys missing
        data.setdefault("exact_map", {})
        data.setdefault("regex_map", [])
        return data
    return {"exact_map": {}, "regex_map": []}

def canon_accessory(row: pd.Series, amap: dict) -> str | None:
    """
    Försök klassificera raden som 'accessory' baserat på fält som brukar bära typ:
    - object_name.type, object_category, title.type, eller title
    Returnerar t.ex. 'manual', 'soundtrack', 'poster'... eller None.
    """
    candidates = []
    for key in ("object_name.type", "object_category", "title.type", "title"):
        if key in row and pd.notna(row[key]) and str(row[key]).strip():
            candidates.append(str(row[key]))
    if not candidates:
        return None

    text = " | ".join(candidates)

    # exact (fall-insensitive via lower-jämförelse)
    exact = (amap.get("exact_map") or {})
    lower_text = text.lower()
    for raw, code in exact.items():
        if raw and str(raw).lower() in lower_text:
            return code

    # regex
    for spec in (amap.get("regex_map") or []):
        if re.search(spec.get("pattern", ""), text, flags=re.IGNORECASE):
            return spec.get("code")

    return None

# --- Stränghjälpare -----------------------------------------------------------
def split_on_many(val: str | None, delimiters=(";", "|")) -> list[str]:
    """Dela sträng på flera delimiters och trimma whitespace."""
    if val is None:
        return []
    s = str(val)
    for d in delimiters:
        s = s.replace(d, "|")
    return [x.strip() for x in s.split("|") if x.strip()]

# --- Titel-normalisering ------------------------------------------------------
def split_title(title: str | None) -> tuple[str, str]:
    """
    Dela 'title' till:
    - title_primary = första titeln
    - alt_titles = övriga, hopslagna med '|'
    """
    parts = split_on_many(title, delimiters=(";", "|"))
    if not parts:
        return "", ""
    primary = parts[0]
    alts = "|".join(parts[1:]) if len(parts) > 1 else ""
    return primary, alts

# --- Huvudflöde ---------------------------------------------------------------
def main():
    csvs = sorted(RAW_DIR.rglob("*.csv"))
    if not csvs:
        print("❌ Hittade inga CSV i data/raw/. Lägg dit filer och kör igen.")
        return

    pmap = load_platform_map()
    amap = load_accessory_map()

    summary_rows = []
    debug_dir = OUT_DIR / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    for path in csvs:
        print(f"[NORMALIZE] Läser: {path}")
        df, used_enc, used_sep = read_csv_auto(path)
        print(f"- Upptäckt encoding: {used_enc} | separator: {repr(used_sep)}")
        print(f"- Form (före): {df.shape[0]} rader × {df.shape[1]} kolumner")

        platform_col = "object_name"
        title_col = "title"

        # platform + title
        df["platform_raw_first"] = df[platform_col].apply(
            lambda v: (split_on_many(v, delimiters=(";", "|")) or [None])[0]
        )
        df["platform_norm"] = df["platform_raw_first"].apply(lambda v: canon_platform(v, pmap))
        df[["title_primary", "alt_titles"]] = df.apply(
            lambda r: pd.Series(split_title(r.get(title_col))), axis=1
        )

        # accessories
        df["accessory_type"] = df.apply(lambda r: canon_accessory(r, amap), axis=1)
        mask_acc = df["accessory_type"].notna()
        df.loc[mask_acc, "platform_norm"] = df.loc[mask_acc, "platform_norm"].where(df["platform_norm"].notna(), None)

        # --- metrics per fil ---
        rows = len(df)
        acc = int(df["accessory_type"].notna().sum())
        games = rows - acc
        unknown_games = int(((df["platform_norm"].isna()) & df["accessory_type"].isna()).sum())
        known_games = games - unknown_games
        map_rate = 0.0 if games == 0 else round(100 * known_games / games, 1)

        # accessory breakdown (compact)
        acc_breakdown = "; ".join([f"{k}:{v}" for k, v in df["accessory_type"].value_counts().to_dict().items()])

        summary_rows.append({
            "file": path.name,
            "rows": rows,
            "games(non-accessory)": games,
            "accessories": acc,
            "unknown_platforms(games)": unknown_games,
            "platform_map_rate_%(games)": map_rate,
            "encoding": used_enc,
            "sep": used_sep,
            "accessories_breakdown": acc_breakdown,
        })

        # --- UNKNOWN check ---
        unknown = df[(df["platform_norm"].isna()) & (df["accessory_type"].isna())]
        if not unknown.empty:
            print(f"⚠️ UNKNOWN i {path.name}: {len(unknown)} rader")
            with pd.option_context("display.max_colwidth", 80):
                print(unknown[["object_number", "platform_raw_first", "title"]].head(10).to_string(index=False))
        else:
            print("✅ Inga UNKNOWN i denna fil.")

            
        # --- debug per fil ---
        out_path = debug_dir / f"_debug_normalized_{path.stem}.csv"
        cols_to_save = [
            "object_number", "title", "title.type",
            "object_name", "platform_raw_first", "platform_norm",
            "object_name.type", "object_category",
            "broadcast_standard", "title.language", "place_of_publication",
            "title_primary", "alt_titles", "accessory_type",
        ]
        cols_to_save = [c for c in cols_to_save if c in df.columns or c in
                        ["platform_raw_first","platform_norm","title_primary","alt_titles","accessory_type"]]
        df[cols_to_save].to_csv(out_path, index=False, encoding="utf-8")
        print(f"✅ Skrev debug-fil: {out_path}\n")



    # --- Snygg sammanfattning över alla filer ---
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_df = pd.DataFrame(summary_rows)

    # totalrad (viktad map-rate över alla games)
    total_games = int(summary_df["games(non-accessory)"].sum())
    total_unknown = int(summary_df["unknown_platforms(games)"].sum())
    total_map_rate = 0.0 if total_games == 0 else round(100 * (total_games - total_unknown) / total_games, 1)

    totals = pd.DataFrame([{
        "file": "TOTAL",
        "rows": int(summary_df["rows"].sum()),
        "games(non-accessory)": total_games,
        "accessories": int(summary_df["accessories"].sum()),
        "unknown_platforms(games)": total_unknown,
        "platform_map_rate_%(games)": total_map_rate,
        "encoding": "",
        "sep": "",
        "accessories_breakdown": "",
    }])

    out_summary = OUT_DIR / "_normalize_summary.csv"
    pd.concat([summary_df, totals], ignore_index=True).to_csv(out_summary, index=False, encoding="utf-8")

    print("\n=== NORMALIZE SUMMARY ===")
    with pd.option_context("display.max_colwidth", 120, "display.width", 160):
        print(summary_df.to_string(index=False))
        print("\nTOTALS:")
        print(totals.to_string(index=False))
    print(f"\n📄 Sparade sammanfattning: {out_summary}")


if __name__ == "__main__":
    main()
