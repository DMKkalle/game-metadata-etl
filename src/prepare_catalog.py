# src/prepare_catalog.py
# -*- coding: utf-8 -*-
"""
Förbereder hela katalogdumpen (fullexport.csv) till ett rent, neutralt underlag.

IN : data/raw/fullexport.csv
OUT: data/outputs/catalog_prepared.csv

Det här görs:
- robust CSV-läsning (sniffar delimiter, hanterar BOM)
- väljer & döper om till vårt grundschema
- städar språklistor ("English;Japanese;;" -> "English; Japanese")
- trimmar whitespace
- hoppar helt tomma rader
"""

from __future__ import annotations
import csv, os
from pathlib import Path
from typing import Dict, Any

IN  = Path("data/raw/fullexport.csv")
OUT = Path("data/outputs/catalog_prepared.csv")

FIELDS = [
    "source","source_id",
    "title_primary","platform","media",
    "broadcast_standard","languages","country","category",
]

def clean_lang(s: str) -> str:
    toks = [t.strip() for t in (s or "").split(";")]
    toks = [t for t in toks if t]
    seen, out = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t); out.append(t)
    return "; ".join(out)

def dict_reader_smart(path: Path):
    """
    Robust DictReader:
    - sniffar delimiter bland , ; \t |
    - hanterar BOM
    - lägger extra kolumner i __rest__ och ignorerar dem
    - alla värden normaliseras till str
    """
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",",";","\t","|"])
        except Exception:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect, restkey="__rest__", restval="")
        for row in reader:
            clean: Dict[str, Any] = {}
            for k, v in row.items():
                key = ("" if k is None else str(k)).strip()
                if key == "__rest__":
                    continue
                if isinstance(v, list):
                    v = "; ".join([(("" if x is None else str(x)).strip()) for x in v])
                else:
                    v = ("" if v is None else str(v)).strip()
                clean[key] = v
            yield clean

def main():
    if not IN.exists():
        raise FileNotFoundError(f"Hittar inte {IN}. Lägg filen där först.")
    os.makedirs(OUT.parent, exist_ok=True)

    n = 0
    with OUT.open("w", encoding="utf-8", newline="") as g:
        w = csv.DictWriter(g, fieldnames=FIELDS)
        w.writeheader()
        for row in dict_reader_smart(IN):
            out = {
                "source": "catalog",
                "source_id": row.get("object_number",""),
                "title_primary": row.get("title",""),
                "platform": row.get("object_name",""),
                "media": row.get("object_name.type",""),
                "broadcast_standard": row.get("broadcast_standard",""),
                "languages": clean_lang(row.get("title.language","")),
                "country": row.get("place_of_publication",""),
                "category": row.get("object_category",""),
            }
            # hoppa tomma rader (saknar identitet + titel + plattform)
            if not (out["source_id"] or out["title_primary"] or out["platform"]):
                continue
            w.writerow(out); n += 1
    print(f"[WRITE] {OUT} ({n} rader)")

if __name__ == "__main__":
    main()
