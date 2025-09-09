"""
normalize_one.py — Steg 2: Normalisera EN rå-CSV (förhandsvisning)
Syfte:
- Läsa första CSV i data/raw/
- Normalisera plattform -> 'platform_norm' (SNES/SFC/…)
- Dela titel -> 'title_primary' + 'alt_titles'
- INTE ändra originalet. Skriv bara en debug-fil till data/outputs/_debug_normalized.csv

Körning:
    python src/normalize_one.py

Krav:
- pandas, pyyaml
- configs/platform_map.yaml (frivilligt, men rekommenderas)
"""

from pathlib import Path
import re
import pandas as pd
import yaml

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/outputs")
PLATFORM_MAP_PATH = Path("configs/platform_map.yaml")

# --- Hjälpare: robust CSV-läsning (samma som i peek_raw) ---------------------
def read_csv_auto(p: Path, encodings=("utf-8","latin1","utf-16"), seps=(",", ";", "\t")):
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

def split_on_many(val: str | None, delimiters=(";","|")) -> list[str]:
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
    # 1) Välj EN CSV i data/raw (vi kör långsamt och kontrollerat).
    csvs = sorted(RAW_DIR.rglob("*.csv"))
    if not csvs:
        print("❌ Hittade inga CSV i data/raw/. Lägg dit en fil och kör igen.")
        return
    path = csvs[0]
    print(f"[NORMALIZE] Läser: {path}")

    # 2) Läs in robust
    df, used_enc, used_sep = read_csv_auto(path)
    print(f"- Upptäckt encoding: {used_enc} | separator: {repr(used_sep)}")
    print(f"- Form (före): {df.shape[0]} rader × {df.shape[1]} kolumner")

    # 3) Ladda plattformskartan (konfigstyrd)
    pmap = load_platform_map()

    # 4) Gör nya kolumner: platform_norm, title_primary, alt_titles
    platform_col = "object_name"              # från din fil
    title_col = "title"                       # från din fil

    # Flagga om cellen verkar innehålla flera plattformar (vi exploderar INTE än)
    df["platform_raw_first"] = df[platform_col].apply(
        lambda v: (split_on_many(v, delimiters=(";", "|")) or [None])[0]
    )
    df["platform_norm"] = df["platform_raw_first"].apply(lambda v: canon_platform(v, pmap))

    df[["title_primary", "alt_titles"]] = df.apply(
        lambda r: pd.Series(split_title(r.get(title_col))), axis=1
    )

    # 5) Snabb sammanfattning för ögat
    total = len(df)
    known = df["platform_norm"].notna().sum()
    unknown = total - known
    print(f"- platform_norm satt på {known}/{total} rader ({known/total:.1%})")
    if unknown:
        print(f"  ⚠️ Okänd plattform på {unknown} rader (kan bero på ovanliga strängar).")

    print("\n--- Exempel (5 rader) ---")
    with pd.option_context("display.max_colwidth", 120, "display.width", 200):
        print(df[["object_number","platform_raw_first","platform_norm","title_primary","alt_titles"]].head(5).to_string(index=False))

    # 6) Skriv en liten debug-fil så vi kan öppna i Excel/VSCode och kika
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "_debug_normalized.csv"
    cols_to_save = [
        "object_number", "title", "title.type",
        "object_name", "platform_raw_first", "platform_norm",
        "object_name.type", "object_category",
        "broadcast_standard", "title.language", "place_of_publication",
        "title_primary", "alt_titles",
    ]
    # Spara bara de kolumner som faktiskt finns
    cols_to_save = [c for c in cols_to_save if c in df.columns or c in ["platform_raw_first","platform_norm","title_primary","alt_titles"]]
    df[cols_to_save].to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n✅ Skrev debug-fil: {out_path}")

if __name__ == "__main__":
    main()
