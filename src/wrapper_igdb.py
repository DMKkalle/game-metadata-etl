# src/fill_igdb_from_editions.py
# -*- coding: utf-8 -*-
"""
Fyller på den lokala IGDB-dumpen med saknade titlar från en editions-fil
genom att prova flera titelvarianter (original, städad, roman<->siffra).

Exempel:
  python src/fill_igdb_from_editions.py ^
    --editions data/outputs/editions_snes_full.csv ^
    --links data/outputs/edition_links_snes.csv ^
    --batch 800 --sleep-ms 200
"""

from __future__ import annotations
import argparse, csv, os, re, subprocess, time, unicodedata
from pathlib import Path
from typing import Dict, List, Set

def ascii_norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii","ignore").decode("ascii")
    s = re.sub(r"[\W_]+"," ",s).strip().lower()
    s = re.sub(r"\s+"," ",s)
    return s

_ROMAN = {"i":1,"v":5,"x":10,"l":50,"c":100,"d":500,"m":1000}
def roman_to_int(tok: str) -> int:
    t = (tok or "").lower()
    if not t or any(ch not in _ROMAN for ch in t): return -1
    total, prev = 0, 0
    for ch in reversed(t):
        val = _ROMAN[ch]
        if val < prev: total -= val
        else: total += val; prev = val
    return total

def int_to_roman(n: int) -> str:
    if n <= 0: return ""
    vals = [(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),
            (100,'C'),(90,'XC'),(50,'L'),(40,'XL'),
            (10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]
    s=""; 
    for v,r in vals:
        while n>=v: s+=r; n-=v
    return s

# ---- title cleaners/variants ----
_EDITION_NOISE = [
    "players choice","greatest hits","platinum","selects",
    "limited edition","collector","complete in box","cib",
    "boxed","not for resale","demo","sample","promo",
    "bundle","pack","with manual","w/ manual","cart only",
    "loose","jpn","usa","eur","pal","ntsc","ntsc-j","ntsc-u"
]
_BRACKET_RE = re.compile(r"[\(\[\{＜【（].+?[＞】）\}\]\)]")
_DASH_SPLIT_RE = re.compile(r"\s[-–—]\s")
_MULTI_SPACE = re.compile(r"\s+")

def clean_title_for_match(s: str) -> str:
    s = s or ""
    s = _BRACKET_RE.sub(" ", s)
    s = _DASH_SPLIT_RE.split(s, maxsplit=1)[0]
    s = s.replace("™","").replace("®","").replace("©","")
    s = s.lower()
    for w in _EDITION_NOISE:
        s = s.replace(w, " ")
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s

def roman_digit_variants(title: str) -> Set[str]:
    base = ascii_norm(title)
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
            try:
                a2r.append(ascii_norm(int_to_roman(int(w))))
            except:
                a2r.append(w)
        else:
            a2r.append(w)
    out.add(" ".join([w for w in a2r if w]))
    return {v for v in out if v}

# ---- csv helpers ----
def dict_reader_smart(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(8192); f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",",";","\t","|"])
        except Exception:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect, restkey="__rest__", restval="")
        for row in reader:
            clean = {}
            for k, v in row.items():
                key = ("" if k is None else str(k)).strip()
                if key == "__rest__": continue
                if isinstance(v, list):
                    v = "; ".join([(("" if x is None else str(x)).strip()) for x in v])
                else:
                    v = ("" if v is None else str(v)).strip()
                clean[key.lower()] = v
            yield clean

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--editions", type=Path, required=True)
    ap.add_argument("--links", type=Path, required=True)
    ap.add_argument("--batch", type=int, default=500)
    ap.add_argument("--sleep-ms", type=int, default=200)
    args = ap.parse_args()

    # 1) Indexera editions
    ed_index: Dict[str, dict] = {}
    for e in dict_reader_smart(args.editions):
        eid = e.get("edition_id") or e.get("id")
        if not eid: continue
        ed_index[eid] = e

    # 2) Plocka saknade länkar
    missing: List[str] = []
    for l in dict_reader_smart(args.links):
        if not (l.get("igdb_game_id") or "").strip():
            eid = l.get("edition_id") or l.get("id")
            if not eid: continue
            e = ed_index.get(eid)
            if not e: continue
            t = e.get("title_primary") or e.get("title") or e.get("name")
            if t: missing.append(t)

    # 3) Bygg kandidatqueries per titel (orig + cleaned + roman/digit)
    queries: List[str] = []
    seen: Set[str] = set()
    for t in missing:
        c = clean_title_for_match(t)
        for q in {t.strip(), c} | roman_digit_variants(c or t):
            q = q.strip()
            if not q: continue
            if q not in seen:
                seen.add(q); queries.append(q)
        if len(queries) >= args.batch:
            break

    # 4) Kör igdb_extract.py för varje kandidat (dubbletter hanteras där)
    print(f"[FILL] Will query {len(queries)} IGDB titles …")
    for i, q in enumerate(queries, 1):
        try:
            subprocess.run(["python", "src/igdb_extract.py", q], check=False)
        except Exception as ex:
            print(f"[WARN] extract failed for '{q}': {ex}")
        time.sleep(args.sleep_ms / 1000.0)
    print("[FILL] Done.")

if __name__ == "__main__":
    main()
