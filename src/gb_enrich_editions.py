# src/gb_enrich_editions.py
from __future__ import annotations
import argparse, csv, re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd

from gb_client import search_games, game_detail, game_releases, join_names

ED_PATH = Path("data/outputs/editions.csv")
OUT_DIR = Path("data/outputs/enrichment")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / "giantbomb_enrichment.csv"

PLATFORM_GROUPS: Dict[str, List[str]] = {
    "SFC":  ["Super Famicom", "Super Nintendo Entertainment System"],
    "SNES": ["Super Nintendo Entertainment System", "Super Famicom"],
}
PLATFORM_YEAR_RANGE: Dict[str, Tuple[int,int]] = {
    "SFC":  (1990, 1998),
    "SNES": (1990, 1998),
}
STOPWORDS = {"the","and","of","in","edition","remaster","collection","hd","ultimate","deluxe","game"}

ROMAN_MAP = {
    "i":1,"ii":2,"iii":3,"iv":4,"v":5,"vi":6,"vii":7,"viii":8,"ix":9,"x":10,
    "xi":11,"xii":12,"xiii":13,"xiv":14,"xv":15,"xvi":16,"xvii":17,"xviii":18,"xix":19,"xx":20
}

def norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def normalize_title(s: str) -> str:
    s = (s or "").replace("×","x").replace("✕","x").replace("✖","x")
    s = s.replace("—","-").replace("–","-")
    s = re.sub(r"[(){}\[\]]", " ", s)
    return norm_spaces(s)

def title_tokens(s: str) -> List[str]:
    s = normalize_title(s).lower()
    toks = re.split(r"[^a-z0-9]+", s)
    toks = [t for t in toks if t and t not in STOPWORDS]
    return toks

def extract_numbers(s: str) -> List[int]:
    """Hämta numeriska markörer: arabiska (2020,96,2) + romerska (ii, iii, …) normaliserade till int."""
    s = normalize_title(s).lower()
    nums = [int(n) for n in re.findall(r"\b\d+\b", s)]
    romans = [ROMAN_MAP[g] for g in re.findall(r"\b(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx)\b", s)]
    return sorted(set(nums + romans))

def token_overlap(a: str, b: str) -> int:
    A = set(title_tokens(a))
    B = set(title_tokens(b))
    return len(A & B)

def score_title(query: str, name: str) -> int:
    qn = normalize_title(query).lower()
    nn = normalize_title(name).lower()
    if qn and nn and qn == nn:
        return 4  # exakt match → högst
    return token_overlap(query, name)  # 0..N

def platform_match(plat_norm: str, candidate_platforms: List[dict]) -> int:
    wanted = PLATFORM_GROUPS.get(plat_norm, [])
    if not wanted:
        return 0
    cand_names = [norm_spaces((p or {}).get("name", "")) for p in (candidate_platforms or [])]
    return 1 if any(p and p in wanted for p in cand_names) else 0

def parse_year(dt: str) -> Optional[int]:
    if not dt:
        return None
    try:
        return int(dt[:4])
    except Exception:
        return None

def in_platform_year_range(plat_norm: str, year: Optional[int]) -> bool:
    if year is None:
        return True
    lo, hi = PLATFORM_YEAR_RANGE.get(plat_norm, (1900, 2100))
    return lo <= year <= hi

def numbers_compatible(q: str, n: str) -> bool:
    """Siffror/romerska i titlarna ska antingen vara tomma i båda – eller samma uppsättning."""
    qa = extract_numbers(q)
    nb = extract_numbers(n)
    if not qa and not nb:
        return True
    return set(qa) == set(nb)

def pick_best_hit(title: str, plat_norm: str, hits: List[dict]) -> Tuple[Optional[dict], Tuple[int,int]]:
    keep: List[Tuple[Tuple[int,int,int], dict]] = []
    for h in (hits or []):
        tscore = score_title(title, h.get("name",""))
        pmatch = platform_match(plat_norm, h.get("platforms") or [])
        year   = parse_year(h.get("original_release_date") or "")
        year_ok = 1 if in_platform_year_range(plat_norm, year) else 0

        if pmatch != 1:
            continue
        # kräver minst 3 tokens överlapp eller exakt=4
        if tscore < 3 and tscore != 4:
            continue
        # nummer måste lira (t.ex. “’96” ↔ inte “2”)
        if not numbers_compatible(title, h.get("name","")):
            continue

        keep.append(((pmatch, tscore, year_ok), h))

    if not keep:
        return None, (0,0)

    keep.sort(key=lambda x: x[0], reverse=True)
    top = keep[0]
    return top[1], (top[0][0], top[0][1])

def format_release_dates_all(rels: List[dict]) -> str:
    out = []
    for r in rels or []:
        dt = r.get("release_date") or r.get("date_added") or ""
        plat = ((r.get("platform") or {}).get("name")) or ""
        reg  = ((r.get("region") or {}).get("name")) or ""
        if dt and plat:
            out.append(f"{dt} <{plat}{(' | '+reg) if reg else ''}>")
    return " | ".join(out)

def first_platform_release(rels: List[dict], accepted_platform_names: List[str]) -> Tuple[str, str]:
    cand = []
    for r in rels or []:
        plat = ((r.get("platform") or {}).get("name")) or ""
        if plat not in accepted_platform_names:
            continue
        dt = r.get("release_date") or r.get("date_added") or ""
        if not dt:
            continue
        try:
            d = datetime.fromisoformat(dt.split(" ")[0]).date()
            cand.append((d.isoformat(), ((r.get("region") or {}).get("name")) or ""))
        except Exception:
            cand.append((dt, ((r.get("region") or {}).get("name")) or ""))
    if not cand:
        return "", ""
    cand.sort(key=lambda x: (x[0] or "9999-99-99"))
    return cand[0]

def enrich_row(edition_id: str, title: str, plat: str) -> dict:
    hits = search_games(title, limit=12)
    best, conf = pick_best_hit(title, plat, hits)

    def _empty():
        return {
            "edition_id": edition_id,
            "title_primary": title,
            "platform": plat,
            "igdb_id": "", "igdb_name": "",
            "genres": "",
            "developers_for_platform": "",
            "publishers_for_platform": "",
            "release_date_for_platform": "",
            "region_for_platform": "",
            "platforms_all": "",
            "release_dates_all": "",
            "cover_url": "",
            "confidence": f"{conf[0]}/{conf[1]}",
            "source": "giantbomb",
        }

    if not best:
        return _empty()

    gid = best.get("id")
    details = game_detail(gid) or {}
    rels = game_releases(gid, limit=200) or []

    group = PLATFORM_GROUPS.get(plat, [])
    date_for_plat, region_for_plat = first_platform_release(rels, group)
    if group and not date_for_plat:
        return _empty()

    name = details.get("name","")
    genres = join_names(details.get("genres"))
    devs = join_names(details.get("developers"))
    pubs = join_names(details.get("publishers"))
    plats_all = join_names(details.get("platforms"))
    cover = (details.get("image") or {}).get("super_url") or (details.get("image") or {}).get("medium_url") or ""
    releases_all = format_release_dates_all(rels)

    return {
        "edition_id": edition_id,
        "title_primary": title,
        "platform": plat,
        "igdb_id": gid,
        "igdb_name": name,
        "genres": genres,
        "developers_for_platform": devs,
        "publishers_for_platform": pubs,
        "release_date_for_platform": date_for_plat,
        "region_for_platform": region_for_plat,
        "platforms_all": plats_all,
        "release_dates_all": releases_all,
        "cover_url": cover,
        "confidence": f"{conf[0]}/{conf[1]}",
        "source": "giantbomb",
    }

def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Enrich editions via Giant Bomb (strikt matchning + siffercheck)")
    ap.add_argument("--in", dest="in_csv", default=str(ED_PATH), help="Path till editions.csv")
    ap.add_argument("--out", dest="out_csv", default=str(OUT_FILE), help="Output CSV")
    ap.add_argument("--limit", type=int, default=100, help="Max antal editioner att köra")
    ap.add_argument("--platform_whitelist", nargs="*", default=[], help="Filtrera på plattformskoder (t.ex. SFC SNES)")
    args = ap.parse_args()

    df = pd.read_csv(args.in_csv, dtype=str).fillna("")
    df = df.drop_duplicates(subset=["edition_id"]).reset_index(drop=True)
    if args.platform_whitelist:
        df = df[df["platform"].isin(set(args.platform_whitelist))]
    if args.limit > 0:
        df = df.head(args.limit)

    rows = []
    for i, r in df.iterrows():
        eid = r.get("edition_id","")
        title = r.get("title_primary","")
        plat = r.get("platform","")
        print(f"[{i+1}/{len(df)}] {title} ({plat}) …")
        try:
            rows.append(enrich_row(eid, title, plat))
        except Exception as e:
            print(f"   ! Fel: {e}")
            rows.append({
                "edition_id": eid, "title_primary": title, "platform": plat,
                "igdb_id":"", "igdb_name":"", "genres":"", "developers_for_platform":"",
                "publishers_for_platform":"", "release_date_for_platform":"", "region_for_platform":"",
                "platforms_all":"", "release_dates_all":"", "cover_url":"", "confidence":"0/0", "source":"giantbomb"
            })

    out_cols = [
        "edition_id","title_primary","platform",
        "igdb_id","igdb_name","genres",
        "developers_for_platform","publishers_for_platform",
        "release_date_for_platform","region_for_platform",
        "platforms_all","release_dates_all","cover_url","confidence","source"
    ]
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_cols)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"✅ Skrev {len(rows)} rader → {args.out_csv}")

if __name__ == "__main__":
    main()
