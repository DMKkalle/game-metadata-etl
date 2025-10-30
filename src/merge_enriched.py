#!/usr/bin/env python3
import csv
import argparse
from pathlib import Path

PREF_GB = "giantbomb"
PREF_IG = "igdb"

# Fält vi väljer från källor (GB först, IGDB fallback)
FIELD_MAP = [
    ("name",                    ["igdb_name"]),  # heter 'igdb_name' i båda era filer
    ("genres",                  ["genres"]),
    ("developers_for_platform", ["developers_for_platform"]),
    ("publishers_for_platform", ["publishers_for_platform"]),
    ("release_date_for_platform", ["release_date_for_platform"]),
    ("region_for_platform",     ["region_for_platform"]),
    ("platforms_all",           ["platforms_all"]),
    ("release_dates_all",       ["release_dates_all"]),
    ("cover_url",               ["cover_url"]),  # kan droppas senare om du inte vill ha bilder
]

def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def as_keyed(rows: list[dict], key="edition_id") -> dict:
    out = {}
    for r in rows:
        eid = r.get(key)
        if eid and eid not in out:
            out[eid] = r
        elif eid:
            # om dubletter, behåll första
            pass
    return out

def pick(primary: dict|None, secondary: dict|None, col: str) -> tuple[str,str]:
    """Return (value, source_label) med GB som primär."""
    v = ""
    src = ""
    if primary:
        v = (primary.get(col) or "").strip()
        if v:
            return v, PREF_GB
    if secondary:
        v = (secondary.get(col) or "").strip()
        if v:
            return v, PREF_IG
    return "", ""

def main():
    ap = argparse.ArgumentParser(description="Merge GiantBomb (primär) + IGDB (fallback) till golden editions CSV.")
    ap.add_argument("--gb",  default="data/external/giantbomb/giantbomb_enrichment.csv", help="Path till GiantBomb enrichment CSV")
    ap.add_argument("--igdb",default="data/external/igdb/igdb_enrichment.csv",          help="Path till IGDB enrichment CSV")
    ap.add_argument("--out", default="data/processed/editions_enriched.csv",            help="Output path")
    args = ap.parse_args()

    p_gb   = Path(args.gb)
    p_igdb = Path(args.igdb)
    p_out  = Path(args.out)
    p_out.parent.mkdir(parents=True, exist_ok=True)

    gb_rows   = read_csv(p_gb)   if p_gb.exists()   else []
    igdb_rows = read_csv(p_igdb) if p_igdb.exists() else []

    gb_by   = as_keyed(gb_rows)
    igdb_by = as_keyed(igdb_rows)

    # Samla alla edition_ids vi känner till
    all_ids = set(gb_by.keys()) | set(igdb_by.keys())

    header = [
        "edition_id","title_primary","platform",
        "gb_game_id","igdb_game_id",
        "name","genres","developers_for_platform","publishers_for_platform",
        "release_date_for_platform","region_for_platform",
        "platforms_all","release_dates_all","cover_url",
        "primary_source"
    ]

    with p_out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)

        for eid in sorted(all_ids):
            g = gb_by.get(eid)
            i = igdb_by.get(eid)

            # IDs
            gb_game_id  = (g.get("igdb_id").strip() if g and g.get("igdb_id") else "")  # i er GB-fil heter kolumnen tyvärr igdb_id men innehåller GB ID
            igdb_game_id = (i.get("igdb_id").strip() if i and i.get("igdb_id") else "")

            # Basmetadata (titel/plattform) kan komma från antingen; GB föredras
            title = (g.get("title_primary") if g and g.get("title_primary") else (i.get("title_primary") if i else "")) or ""
            plat  = (g.get("platform")      if g and g.get("platform")      else (i.get("platform")      if i else "")) or ""

            # Fältvis hopslagning
            chosen = {}
            sources_used = set()
            for out_col, source_cols in FIELD_MAP:
                # våra två filer råkar ha samma kolumnnamn för dessa nycklar
                col = source_cols[0]
                val, src = pick(g, i, col)
                chosen[out_col] = val
                if src:
                    sources_used.add(src)

            primary_source = PREF_GB if PREF_GB in sources_used else (PREF_IG if PREF_IG in sources_used else "")

            w.writerow([
                eid, title, plat,
                gb_game_id, igdb_game_id,
                chosen["name"], chosen["genres"], chosen["developers_for_platform"], chosen["publishers_for_platform"],
                chosen["release_date_for_platform"], chosen["region_for_platform"],
                chosen["platforms_all"], chosen["release_dates_all"], chosen["cover_url"],
                primary_source
            ])

    print(f"Klart. Skrev merge till {p_out}")

if __name__ == "__main__":
    main()
