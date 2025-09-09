# src/add_region.py
# Lägger till region_norm till master_v1 baserat på broadcast_standard + place_of_publication.

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MASTER_IN = ROOT / "data" / "outputs" / "master_v1.csv"
RAW_IN    = ROOT / "data" / "outputs" / "_debug_normalized.csv"
OUT       = ROOT / "data" / "outputs" / "master_v2.csv"

COUNTRY_TO_REGION = {
    # NTSC-J
    "Japan": "NTSC-J",

    # NTSC-U
    "USA": "NTSC-U", "United States": "NTSC-U", "U.S.A.": "NTSC-U",

    # PAL (Europa m.fl.)
    "Sweden": "PAL", "Netherlands": "PAL", "France": "PAL", "Germany": "PAL",
    "Italy": "PAL", "Spain": "PAL", "Europe": "PAL", "United Kingdom": "PAL",
    "UK": "PAL", "Norway": "PAL", "Finland": "PAL", "Denmark": "PAL",
}


def coalesce_region(broadcast_standard, place, title=None) -> str:
    import pandas as pd
    bs = "" if (broadcast_standard is None or (isinstance(broadcast_standard, float) and pd.isna(broadcast_standard))) else str(broadcast_standard)
    pl = "" if (place is None or (isinstance(place, float) and pd.isna(place))) else str(place)
    bs = bs.strip().upper()
    p = pl.strip()

    # 1. Direkt från broadcast_standard
    if bs in {"PAL", "NTSC-J", "NTSC-U"}:
        return bs

    # 2. Land → region
    if p in COUNTRY_TO_REGION:
        return COUNTRY_TO_REGION[p]

    if "Japan" in p: return "NTSC-J"
    if any(x in p for x in ["USA", "United States", "U.S.A."]): return "NTSC-U"
    if any(x in p for x in ["Sweden","Netherlands","France","Germany","Italy","Spain",
                            "Europe","United Kingdom","UK","Norway","Finland","Denmark",
                            "Belgium","Portugal","Austria","Switzerland","Ireland","Greece",
                            "Poland","Czech","Czechoslovakia","Hungary","Portugal"]):
        return "PAL"

    # 3. Heuristik för tillbehör
    if title:
        t = title.lower()
        if any(x in t for x in ["controller","mouse","stick","adapter","super game boy","multitap"]):
            return "ACCESSORY"

    # 4. Fallback
    return "UNKNOWN"



def main():
    master = pd.read_csv(MASTER_IN, dtype=str)
    raw = pd.read_csv(RAW_IN, dtype=str)[["object_number","broadcast_standard","place_of_publication"]]

    df = master.merge(raw, on="object_number", how="left")
    df["region_norm"] = df.apply(
        lambda r: coalesce_region(r.get("broadcast_standard"), r.get("place_of_publication"), r.get("title_norm")),
        axis=1
    )


    use_cols = list(master.columns) + ["region_norm"]
    df[use_cols].to_csv(OUT, index=False, encoding="utf-8")
    print(f"[REGION] Wrote {OUT} with {len(df)} rows")
    print(df["region_norm"].value_counts(dropna=False).to_string())

if __name__ == "__main__":
    main()
