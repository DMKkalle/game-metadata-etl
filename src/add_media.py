# src/add_media.py
# Lägger till media_norm till master_v3 baserat på 'object_name.type'

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MASTER_IN = ROOT / "data" / "outputs" / "master_v3.csv"
RAW_IN    = ROOT / "data" / "outputs" / "_debug_normalized.csv"
OUT       = ROOT / "data" / "outputs" / "master_v4.csv"

MEDIA_MAP = {
    "Cartridge": "cartridge",
    "Kassett": "cartridge",
    "Diskette": "disk",
    "Floppy Disk": "disk",
    "CD-ROM": "optical",
    "CD": "optical",
    "LaserDisc": "optical",
    "HuCard": "hucard",
}

def norm_media(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "unknown"
    s = str(v).strip()
    if s in {";", ";;", ";;;;"}:
        return "unknown"
    return MEDIA_MAP.get(s, s.lower() if s else "unknown")


def main():
    master = pd.read_csv(MASTER_IN, dtype=str)
    raw = pd.read_csv(RAW_IN, dtype=str)[["object_number","object_name.type"]].rename(columns={"object_name.type":"object_name_type"})
    df = master.merge(raw, on="object_number", how="left")
    df["media_norm"] = df["object_name_type"].apply(norm_media)

    use_cols = list(master.columns) + ["media_norm"]
    df[use_cols].to_csv(OUT, index=False, encoding="utf-8")
    print(f"[MEDIA] Wrote {OUT} with {len(df)} rows")
    print(df["media_norm"].value_counts(dropna=False).to_string())

if __name__ == "__main__":
    import pandas as pd
    main()
