# src/build_editions.py
# Skapar en unik lista över editioner (en rad per edition_id) + antal objekt.

from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN   = ROOT / "data" / "outputs" / "master_v5.csv"
OUT  = ROOT / "data" / "outputs" / "editions.csv"

KEEP = ["edition_id","platform_norm","title_norm","region_norm","language_norm","media_norm"]

df = pd.read_csv(IN, dtype=str)

# räkna objekt per edition och samla object_numbers
grp = df.groupby("edition_id", as_index=False).agg({
    "platform_norm":"first",
    "title_norm":"first",
    "region_norm":"first",
    "language_norm":"first",
    "media_norm":"first",
    "object_number": lambda s: "|".join(sorted(s.astype(str)))
})
grp["objects_count"] = grp["object_number"].str.count(r"\|").add(1)

# ordna kolumner
grp = grp[KEEP + ["objects_count","object_number"]]

OUT.parent.mkdir(parents=True, exist_ok=True)
grp.to_csv(OUT, index=False, encoding="utf-8")
print(f"[EDITIONS] Wrote {OUT} with {len(grp)} editions")
