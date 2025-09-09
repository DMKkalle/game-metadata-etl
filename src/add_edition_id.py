# src/add_edition_id.py
# Bygger en editionsnyckel och stabil edition_id (hash) av kända signaler.

from pathlib import Path
import pandas as pd
import hashlib

ROOT = Path(__file__).resolve().parents[1]
IN   = ROOT / "data" / "outputs" / "master_v4.csv"
OUT  = ROOT / "data" / "outputs" / "master_v5.csv"

KEY_COLS = ["platform_norm","title_norm","region_norm","language_norm","media_norm"]

def make_key(row: pd.Series) -> str:
    vals = [str(row.get(c,"") or "").strip() for c in KEY_COLS]
    return " | ".join(vals)

def make_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]  # kort, men stabil

def main():
    df = pd.read_csv(IN, dtype=str)
    for c in KEY_COLS:
        if c not in df.columns:
            raise SystemExit(f"Missing column: {c}")
    df["edition_key"] = df.apply(make_key, axis=1)
    df["edition_id"]  = df["edition_key"].apply(make_hash)
    df.to_csv(OUT, index=False, encoding="utf-8")
    print(f"[EDITION] Wrote {OUT} with {len(df)} rows")
    # liten vy: hur många unika editions kontra objekt
    n_objects = len(df)
    n_editions = df["edition_id"].nunique()
    print(f"[EDITION] Objects: {n_objects} | Editions: {n_editions} | Objects/Edition: {n_objects/n_editions:.2f}")

if __name__ == "__main__":
    main()
