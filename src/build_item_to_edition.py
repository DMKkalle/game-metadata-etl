# src/build_item_to_edition.py
# Skapar en enkel mapping mellan object_number och edition_id.

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN   = ROOT / "data" / "outputs" / "master_v5.csv"
OUT  = ROOT / "data" / "outputs" / "items_to_editions.csv"

df = pd.read_csv(IN, dtype=str)
out = df[["object_number","edition_id","platform_norm","title_norm","region_norm","language_norm","media_norm"]].copy()
OUT.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(OUT, index=False, encoding="utf-8")
print(f"[MAP] Wrote {OUT} with {len(out)} rows and {out['edition_id'].nunique()} unique editions")
