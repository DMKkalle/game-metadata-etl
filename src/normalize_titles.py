# src/normalize_titles.py
# Skapar en kanonisk titel (title_norm) + aliaslista från title_primary och alt_titles.
# Regel:
#  1) Om title_primary är “latinsk/ASCII” → använd den som title_norm.
#  2) Annars: ta första alt_title som är latinsk/ASCII.
#  3) Om ingen latinsk finns → använd title_primary som fallback.
#
# Output: data/outputs/_debug_titles.csv

from __future__ import annotations
import re
import sys
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
IN_PATH = REPO_ROOT / "data" / "outputs" / "_debug_normalized.csv"
OUT_PATH = REPO_ROOT / "data" / "outputs" / "_debug_titles.csv"

ASCII_PATTERN = re.compile(r"[^\x00-\x7F]")  # matchar icke-ASCII

def is_ascii(s: str | None) -> bool:
    if not s:
        return False
    return not ASCII_PATTERN.search(s)

def norm_punct(s: str | None) -> str:
    if not s:
        return ""
    s = (s
         .replace("’","'").replace("‘","'")
         .replace("“",'"').replace("”",'"')
         .replace("–","-").replace("—","-"))
    s = re.sub(r"\s+", " ", s).strip()
    return s

def split_alts(s: str | None) -> list[str]:
    """Dela alt_titles. Primärt '|' annars ; , / . Tål NaN/None."""
    import pandas as pd
    if s is None or (isinstance(s, float) and pd.isna(s)) or (hasattr(pd, "isna") and pd.isna(s)):
        return []
    s = str(s).strip()
    if not s:
        return []
    parts = re.split(r"\|", s)
    if len(parts) == 1:
        parts = re.split(r"[;,/]", s)
    return [p.strip() for p in parts if p.strip()]


def choose_canonical(primary: str, alts: list[str]) -> tuple[str, str]:
    """
    Returnerar (title_norm, title_norm_source)
    title_norm_source ∈ {"primary_ascii", "alt_ascii", "primary_fallback"}
    """
    if primary and is_ascii(primary):
        return primary, "primary_ascii"
    for a in alts:
        if is_ascii(a):
            return a, "alt_ascii"
    # fallback
    return primary or (alts[0] if alts else ""), "primary_fallback"

def main():
    if not IN_PATH.exists():
        print(f"[ERROR] Hittar inte input: {IN_PATH}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(IN_PATH, dtype=str)  # bevara strängar som str
    # Försäkra att kolumnerna finns
    for col in ("object_number", "title_primary", "alt_titles"):
        if col not in df.columns:
            print(f"[ERROR] Saknar kolumn: {col}", file=sys.stderr)
            sys.exit(1)

    out_rows = []
    for _, r in df.iterrows():
        obj = r.get("object_number", "")
        primary_raw = r.get("title_primary", "")
        alts_raw = r.get("alt_titles", "")

        primary = norm_punct(primary_raw)
        alts = [norm_punct(x) for x in split_alts(alts_raw)]

        title_norm, source = choose_canonical(primary, alts)

        out_rows.append({
            "object_number": obj,
            "platform_raw_first": r.get("platform_raw_first", ""),
            "platform_norm": r.get("platform_norm", ""),
            "title_primary": primary,
            "alt_titles": "|".join(alts),  # standardisera till '|'
            "title_norm": title_norm,
            "title_norm_source": source,
            "title_aliases": "|".join([t for t in [primary, *alts] if t and t != title_norm]),
    })


    out = pd.DataFrame(out_rows)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False, encoding="utf-8")
    print(f"[TITLES] Läste:  {IN_PATH}")
    print(f"[TITLES] Skrev:  {OUT_PATH}")
    print(f"[TITLES] Rader:  {len(out)}")
    print("[TITLES] Klart.")

if __name__ == "__main__":
    main()
