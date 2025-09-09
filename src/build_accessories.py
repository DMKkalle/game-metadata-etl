from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN   = ROOT / "data" / "outputs" / "master_v2.csv"
OUT  = ROOT / "data" / "outputs" / "accessories.csv"

df = pd.read_csv(IN, dtype=str)
acc = df[df["region_norm"] == "ACCESSORY"].copy()
acc.to_csv(OUT, index=False, encoding="utf-8")
print(f"[ACC] Wrote {OUT} with {len(acc)} rows")
