# src/link_external.py
# -*- coding: utf-8 -*-
"""
Länkar editions -> externa ID:n (IGDB offline-dump).

- Läser IGDB-CSV från data/external/igdb/
- Stöd för dina rubriker: igdb_id, first_release_date_ymd, platforms (semikolonseparerade namn)
- Läser editions (*.csv) och accepterar title_primary/title/title_norm
- Titel-städning + plattforms-alias (SNES/SFC/Super Famicom)
- Auto-detekt av CSV-delimiter
- Poäng: titel (50%) + plattform (30%) + år (20%)

Usage:
  python src/link_external.py
  # valfritt:
  python src/link_external.py --editions data/outputs/editions_snes_full.csv --out data/outputs/edition_links_snes.csv --min-score 0.40
"""

from __future__ import annotations
import argparse
import csv
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, Set, List, Any

DEFAULT_EDITIONS = Path("data/outputs/editions.csv")
DEFAULT_IGDB_DIR = Path("data/external/igdb")
DEFAULT_OUT = Path("data/outputs/edition_links.csv")

# ---------- text helpers ----------
def ascii_norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[\W_]+", " ", s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

ROMAN_MAP = {"i":1,"v":5,"x":10,"l":50,"c":100,"d":500,"m":1000}

def roman_to_int(token: str) -> int:
    t = (token or "").lower()
    if not t or any(ch not in ROMAN_MAP for ch in t):
        return -1
    total, prev = 0, 0
    for ch in reversed(t):
        val = ROMAN_MAP[ch]
        if val < prev: total -= val
        else: total += val; prev = val
    return total

def int_to_roman(n: int) -> str:
    if n <= 0: return ""
    vals = [(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),
            (100,'C'),(90,'XC'),(50,'L'),(40,'XL'),
            (10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]
    s=""
    for v,r in vals:
        while n>=v: s+=r; n-=v
    return s

def name_variants(title: str) -> Set[str]:
    base = ascii_norm(title or "")
    toks = base.split()
    out = {base}

    # roman -> arabic
    rconv = []
    for w in toks:
        rv = roman_to_int(w)
        rconv.append(str(rv) if rv > 0 else w)
    out.add(" ".join([w for w in rconv if w]))

    # arabic -> roman
    a2r = []
    for w in toks:
        if w.isdigit():
            try: a2r.append(ascii_norm(int_to_roman(int(w))))
            except: a2r.append(w)
        else:
            a2r.append(w)
    out.add(" ".join([w for w in a2r if w]))
    return {v for v in out if v}

def jaccard(a: str, b: str) -> float:
    sa, sb = set((a or "").split()), set((b or "").split())
    if not sa or not sb: return 0.0
    return len(sa & sb) / len(sa | sb)

# --- Title & platform cleaners (lightweight) ---
_EDITION_NOISE = [
    "players choice", "greatest hits", "platinum", "selects",
    "limited edition", "collector", "complete in box", "cib",
    "boxed", "not for resale", "demo", "sample", "promo",
    "bundle", "pack", "with manual", "w/ manual", "cart only",
    "loose", "jpn", "usa", "eur", "pal", "ntsc", "ntsc-j", "ntsc-u"
]
_BRACKET_RE = re.compile(r"[\(\[\{＜【（].+?[＞】）\}\]\)]")
_DASH_SPLIT_RE = re.compile(r"\s[-–—]\s")
_MULTI_SPACE = re.compile(r"\s+")

def clean_title_for_match(s: str) -> str:
    s = s or ""
    s = _BRACKET_RE.sub(" ", s)           # ta bort innehåll inom () [] {} (ofta extrainfo)
    parts = _DASH_SPLIT_RE.split(s, maxsplit=1)
    s = parts[0]                           # ta bort suffix efter " - " (edition/utgåva-info)
    s = s.replace("™","").replace("®","").replace("©","")
    s = s.lower()
    for w in _EDITION_NOISE:
        s = s.replace(w, " ")
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s

PLATFORM_ALIASES = {
    "snes": "super nintendo entertainment system",
    "super nintendo": "super nintendo entertainment system",
    "super nintendo entertainment system": "super nintendo entertainment system",
    "super famicom": "super nintendo entertainment system",
    "sfc": "super nintendo entertainment system",
}
def normalize_platform_name(p: str) -> str:
    p = (p or "").strip().lower()
    return PLATFORM_ALIASES.get(p, p)

# ---------- CSV helpers ----------
def _lower_keys(row: dict) -> dict:
    return {(k or "").strip().lower(): v for k, v in row.items()}

def _pick(row: dict, *cands) -> Any:
    for c in cands:
        if c in row and str(row[c]).strip() != "":
            return row[c]
    return ""

def _year_from_any(s) -> int | None:
    if s is None: return None
    s = str(s).strip()
    m = re.search(r"(19|20)\d{2}", s)
    if m:
        try: return int(m.group(0))
        except: return None
    if s.isdigit():
        try:
            v = int(s)
            if v > 10_000_000_000:  # ms -> s
                v //= 1000
            import datetime
            return datetime.datetime.utcfromtimestamp(v).year
        except: return None
    return None

def dict_reader_smart(path: Path):
    """
    Robust DictReader:
    - utf-8-sig (hanterar BOM)
    - sniffar delimiter bland , ; \t |
    - returnerar rader med lowercased keys
    - ignorerar extra kolumner via restkey
    """
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(8192)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",",";","\t","|"])
        except Exception:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect, restkey="__rest__", restval="")
        for row in reader:
            clean = {}
            for k, v in row.items():
                key = ("" if k is None else str(k)).strip()
                if key == "__rest__":  # extra kolumner → ignorera
                    continue
                if isinstance(v, list):
                    v = "; ".join([(("" if x is None else str(x)).strip()) for x in v])
                else:
                    v = ("" if v is None else str(v)).strip()
                clean[key.lower()] = v
            yield clean

# ---------- IGDB loader ----------
def load_igdb(igdb_dir: Path):
    """
    Laddar:
      - igdb_platforms.csv  -> platforms_by_id[pid] = {name, abbr}
      - igdb_games.csv      -> games[gid] = {name, year, platform_ids:set(), platform_names:set()}
      - igdb_alternative_names.csv (valfri)
      - igdb_release_dates.csv (valfri)
    """
    p_platforms = igdb_dir / "igdb_platforms.csv"
    p_games = igdb_dir / "igdb_games.csv"
    p_alt = igdb_dir / "igdb_alternative_names.csv"
    p_reldates = igdb_dir / "igdb_release_dates.csv"

    missing = [p for p in [p_platforms, p_games] if not p.exists()]
    if missing:
        raise FileNotFoundError("Saknar IGDB-filer: " + ", ".join(str(x) for x in missing))

    platforms_by_id: Dict[int, Dict[str, str]] = {}
    for row in dict_reader_smart(p_platforms):
        pid = _pick(row, "id","platform_id","platforms.id","_id","pk","platform")
        if not str(pid).strip().isdigit(): continue
        pid = int(pid)
        pname = _pick(row, "name","platform_name","platforms.name","title")
        pabbr = _pick(row, "abbreviation","abbr","short_name","short","slug")
        platforms_by_id[pid] = {"name": pname or "", "abbr": pabbr or ""}

    games: Dict[int, Dict[str, Any]] = {}
    for row in dict_reader_smart(p_games):
        # DINA rubriker: igdb_id, first_release_date_ymd, platforms (namnlista)
        gid = _pick(row, "igdb_id","id","game_id","games.id","_id","pk")
        if not str(gid).strip().isdigit(): continue
        gid = int(gid)
        gname = _pick(row, "name","title")
        gy = _year_from_any(_pick(row, "first_release_date_ymd","first_release_date_ts","first_release_date","first_release_year","release_date","created_at","updated_at","date"))
        pnames = [x.strip() for x in (_pick(row, "platforms","platform_names") or "").split(";") if x.strip()]
        games[gid] = {"name": gname or "", "year": gy, "platform_ids": set(), "platform_names": set(pnames)}

    altnames: Dict[int, Set[str]] = {}
    if p_alt.exists():
        for row in dict_reader_smart(p_alt):
            gid = _pick(row, "game","game_id","games.id","id","igdb_id")
            if not str(gid).strip().isdigit(): continue
            gid = int(gid)
            nm = _pick(row, "name","alternative_name","alt_name","title")
            if nm: altnames.setdefault(gid, set()).add(nm)

    if p_reldates.exists():
        for row in dict_reader_smart(p_reldates):
            g = _pick(row, "game","game_id","games.id","id","igdb_id")
            p = _pick(row, "platform","platform_id","platforms.id")
            if str(g).strip().isdigit() and str(p).strip().isdigit():
                gid, pid = int(g), int(p)
                if gid in games:
                    games[gid]["platform_ids"].add(pid)

    # namnindex
    idx: Dict[str, Set[int]] = {}
    def _add(gid: int, nm: str):
        for v in name_variants(nm or ""):
            idx.setdefault(v, set()).add(gid)

    for gid, g in games.items():
        if g["name"]: _add(gid, g["name"])
        for nm in altnames.get(gid, []):
            _add(gid, nm)

    print(f"[IGDB] platforms={len(platforms_by_id)} games={len(games)} name_keys={len(idx)}")
    return games, idx, platforms_by_id

# ---------- scoring ----------
def platform_match_score(our_platform: str, igdb_platform_ids: Set[int], platforms_by_id: Dict[int, Dict[str, str]], game_platform_names: Set[str]) -> float:
    if not our_platform:
        return 0.0
    op = ascii_norm(our_platform)
    best = 0.0
    # ID-baserad
    for pid in igdb_platform_ids or []:
        p = platforms_by_id.get(pid, {})
        cand = max(
            jaccard(op, ascii_norm(p.get("abbr",""))),
            jaccard(op, ascii_norm(p.get("name","")))
        )
        best = max(best, cand)
    # Namn-baserad fallback
    for nm in game_platform_names or []:
        best = max(best, jaccard(op, ascii_norm(nm)))
    return best

def score_candidate(edition_row: dict, game: dict, platforms_by_id: Dict[int, Dict[str, str]]) -> float:
    # titel
    jt = jaccard(edition_row["_title_norm"], ascii_norm(game.get("name","")))
    # år (±5 års avtrappning)
    oy = None
    for k in ("release_year","year","notes"):
        if edition_row.get(k):
            oy = _year_from_any(edition_row.get(k)); 
            if oy: break
    if oy is not None and game.get("year") is not None:
        dy = abs(oy - game["year"])
        yr = max(0.0, 1.0 - min(dy, 5)/5.0)
    else:
        yr = 0.5
    # plattform
    pm = platform_match_score(
        edition_row.get("platform_norm") or edition_row.get("platform") or "",
        game.get("platform_ids", set()),
        platforms_by_id,
        game.get("platform_names", set())
    )
    return 0.5*jt + 0.3*pm + 0.2*yr

# ---------- main flow ----------
def read_editions(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Hittar inte editions: {path}")
    rows = []
    for row in dict_reader_smart(path):
        eid = _pick(row, "edition_id","id","edition","ed_id")
        title_raw = _pick(row, "title_norm","title","title_primary","game_title","name_norm","name")
        if not eid or not title_raw:
            continue
        plat_raw = _pick(row, "platform_norm","platform")
        row["_title_norm"] = ascii_norm(clean_title_for_match(title_raw))
        row["platform_norm"] = normalize_platform_name(plat_raw)
        rows.append(row)
    if not rows:
        print("Varning: Inga editions att länka (fel delimiter/kolumner?).")
    return rows

def link_editions_to_igdb(editions: List[dict], games: Dict[int, dict], name_idx: Dict[str, Set[int]], platforms_by_id: Dict[int, Dict[str, str]], min_score: float = 0.40) -> List[dict]:
    out: List[dict] = []
    matched = 0
    for r in editions:
        eid = _pick(r, "edition_id","id","edition","ed_id")
        # tillbehör? (om du har sådan flagga i dina filer)
        if (str(r.get("is_accessory") or "").strip().lower() in ("1","true","yes")):
            out.append({"edition_id": eid, "igdb_game_id":"", "gb_game_id":"", "score":"", "note":"accessory"})
            continue

        cands: Set[int] = set()
        for v in name_variants(_pick(r, "title_norm","title","title_primary","game_title","name_norm","name")):
            cands |= name_idx.get(v, set())

        best_gid, best_sc = "", 0.0
        for gid in cands:
            sc = score_candidate(r, games[gid], platforms_by_id)
            if sc > best_sc:
                best_sc, best_gid = sc, gid

        if best_gid and best_sc >= min_score:
            matched += 1
            out.append({"edition_id": eid, "igdb_game_id": int(best_gid), "gb_game_id":"", "score": f"{best_sc:.3f}", "note":""})
        else:
            out.append({"edition_id": eid, "igdb_game_id":"", "gb_game_id":"", "score": f"{best_sc:.3f}" if best_sc else "", "note":"no-match"})
    total = len(editions)
    print(f"[LINK] IGDB matchade {matched}/{total} ({(matched/total*100 if total else 0):.1f}%), min_score={min_score}")
    return out

def write_links(path: Path, rows: List[dict]):
    os.makedirs(path.parent, exist_ok=True)
    fields = ["edition_id","igdb_game_id","gb_game_id","score","note"]
    with open(path, "w", newline='', encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"[WRITE] {path} ({len(rows)} rader)")

def parse_args():
    p = argparse.ArgumentParser(description="Länka editions -> IGDB (offline dump).")
    p.add_argument("--editions", type=Path, default=DEFAULT_EDITIONS)
    p.add_argument("--igdb-dir", type=Path, default=DEFAULT_IGDB_DIR)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--min-score", type=float, default=0.40)
    return p.parse_args()

def main():
    args = parse_args()
    games, name_idx, platforms_by_id = load_igdb(args.igdb_dir)
    editions = read_editions(args.editions)
    links = link_editions_to_igdb(editions, games, name_idx, platforms_by_id, min_score=args.min_score)
    write_links(args.out, links)

if __name__ == "__main__":
    main()
