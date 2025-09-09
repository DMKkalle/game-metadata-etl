from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "data" / "outputs" / "_debug_titles.csv"
OUT = ROOT / "data" / "outputs" / "master_v1.csv"

use_cols = [
    "object_number",
    "platform_raw_first",
    "platform_norm",
    "title_primary",
    "title_norm",
    "title_norm_source",
    "title_aliases",
]

df = pd.read_csv(IN, dtype=str)
df = df[use_cols]
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False, encoding="utf-8")
print(f"[MASTER] Wrote {OUT} with {len(df)} rows")
