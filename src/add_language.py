# src/add_language.py
# Lägger till language_norm till master_v2 baserat på 'title.language'

from pathlib import Path
import pandas as pd
import re

ROOT = Path(__file__).resolve().parents[1]
MASTER_IN = ROOT / "data" / "outputs" / "master_v2.csv"
RAW_IN    = ROOT / "data" / "outputs" / "_debug_normalized.csv"
OUT       = ROOT / "data" / "outputs" / "master_v3.csv"

LANG_MAP = {
    "english": "en",
    "japanese": "ja",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "italian": "it",
    "dutch": "nl",
    "swedish": "sv",
    "norwegian": "no",
    "finnish": "fi",
    "danish": "da",
}

def pick_language(s: str) -> str:
    """
    'title.language' kan se ut som: 'Japanese;;', 'English;;;', 'Japanese;Japanese', '', None.
    Välj första icke-tomma token, normalisera till ISO-liknande kod (en/ja/…).
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return "unknown"
    s = str(s)
    # Splitta på ';' och ta första icke-tomma
    toks = [t.strip() for t in s.split(';') if t.strip()]
    lang = toks[0] if toks else ""
    if not lang:
        return "unknown"
    key = lang.lower()
    key = re.sub(r"[^a-z]", "", key)  # ta bort punkter/udda tecken
    return LANG_MAP.get(key, key if key else "unknown")  # fallback: 'japanese'->'ja' etc., annars rå-lägre

def main():
    master = pd.read_csv(MASTER_IN, dtype=str)
    raw = pd.read_csv(RAW_IN, dtype=str)[["object_number", "title.language"]].rename(columns={"title.language": "title_language_raw"})
    df = master.merge(raw, on="object_number", how="left")
    df["language_norm"] = df["title_language_raw"].apply(pick_language)
    use_cols = list(master.columns) + ["language_norm"]
    df[use_cols].to_csv(OUT, index=False, encoding="utf-8")
    print(f"[LANG] Wrote {OUT} with {len(df)} rows")
    print(df["language_norm"].value_counts(dropna=False).to_string())

if __name__ == "__main__":
    main()
