# src/gb_link_from_titles.py
# -*- coding: utf-8 -*-
"""
Länkar befintligt IGDB-länkade editioner till GiantBomb genom titel-sök.
- Läser:  data/outputs/edition_links_snes.csv  (skrivs tillbaka)
          data/outputs/editions_snes_full.csv
- Kräver env: GIANTBOMB_API_KEY
- Säker: uppdaterar enbart gb_game_id för de editioner som får träff.

Usage:
  setx GIANTBOMB_API_KEY "din-nyckel"
  python src/gb_link_from_titles.py --links data/outputs/edition_links_snes.csv --editions data/outputs/editions_snes_full.csv
"""

from __future__ import annotations
import argparse, csv, os, re, time, unicodedata, json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import urllib.parse, urllib.request

def ascii_norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii","ignore").decode("ascii")
    s = re.sub(r"[\W_]+"," ", s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

_BRACKET_RE = re.compile(r"[\(\[\{＜【（].+?[＞】）\}\]\)]")
_DASH_SPLIT_RE = re.compile(r"\s[-–—]\s")
def clean_title(s: str) -> str:
    s = _BRACKET_RE.sub(" ", s or "")
    s = _DASH_SPLIT_RE.split(s, maxsplit=1)[0]
    s = s.replace("™","").replace("®","").replace("©","")
    return re.sub(r"\s+"," ", s).strip()

PLATFORM_ALIASES = {
    "snes":"super nintendo entertainment system",
    "super famicom":"super nintendo entertainment system",
    "nintendo super nintendo entertainment system":"super nintendo entertainment system",
}
def norm_platform(p: str) -> str:
    p = (p or "").strip().lower()
    return PLATFORM_ALIASES.get(p, p)

def jaccard(a: str, b: str) -> float:
    sa, sb = set((a or "").split()), set((b or "").split())
    if not sa or not sb: return 0.0
    return len(sa & sb) / len(sa | sb)

def read_csv(path: Path) -> List[Dict[str,str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write_csv(path: Path, rows: List[Dict[str,str]]):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

def gb_search(api_key: str, query: str) -> Dict[str,Any]:
    # GiantBomb Search API
    params = {
        "api_key": api_key,
        "format": "json",
        "query": query,
        "resources": "game",
        "limit": 10,
    }
    url = "https://www.giantbomb.com/api/search/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent":"exjobb-embracer/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def pick_best_gb(result: Dict[str,Any], want_title: str, want_platform: str) -> Optional[Tuple[str,float]]:
    want_t = ascii_norm(clean_title(want_title))
    want_p = ascii_norm(norm_platform(want_platform))
    best_id, best_score = None, 0.0
    for it in result.get("results", []):
        name = it.get("name") or ""
        platnames = []
        try:
            for p in it.get("platforms") or []:
                # GB ger t.ex. {'name':'Super Nintendo Entertainment System','abbreviation':'SNES'}
                nm = p.get("name") or p.get("abbreviation") or ""
                if nm: platnames.append(ascii_norm(nm))
        except Exception:
            pass
        t_score = jaccard(want_t, ascii_norm(clean_title(name)))
        p_score = 0.0
        for pn in platnames:
            p_score = max(p_score, jaccard(want_p, pn))
        score = 0.7*t_score + 0.3*p_score
        if score > best_score:
            # GB-id går att läsa ur api_detail_url (sista siffror)
            api_url = it.get("api_detail_url") or ""
            gid = None
            m = re.search(r"/(\d+)-?$", api_url.rstrip("/"))
            if m:
                gid = m.group(1)
            elif it.get("id"):
                gid = str(it["id"])
            if gid:
                best_id, best_score = gid, score
    if best_id and best_score >= 0.35:
        return best_id, best_score
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--links", type=Path, required=True)
    ap.add_argument("--editions", type=Path, required=True)
    ap.add_argument("--sleep-ms", type=int, default=200)
    args = ap.parse_args()

    api_key = os.environ.get("GIANTBOMB_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Saknar GIANTBOMB_API_KEY i environment.")

    links = read_csv(args.links)
    ed_index = { r["edition_id"]: r for r in read_csv(args.editions) }

    updated, tried = 0, 0
    for row in links:
        if not row.get("edition_id"): continue
        # vi jobbar bara med poster som redan har IGDB-id (enligt din plan)
        if not (row.get("igdb_game_id") or "").strip(): 
            continue
        # hoppa om GB redan finns
        if (row.get("gb_game_id") or "").strip():
            continue

        e = ed_index.get(row["edition_id"])
        if not e: 
            continue
        title = e.get("title_primary") or e.get("title") or ""
        platform = e.get("platform") or ""
        if not title: 
            continue

        # prova två queries: original och städad variant
        qlist = [title, clean_title(title)]
        best = None
        for q in qlist:
            tried += 1
            try:
                data = gb_search(api_key, q)
                pick = pick_best_gb(data, title, platform)
                if pick:
                    best = pick
                    break
            except Exception as ex:
                # snäll fallback: fortsätt
                pass
            time.sleep(args.sleep_ms/1000.0)

        if best:
            row["gb_game_id"] = best[0]
            updated += 1
            # liten vila mellan lyckade calls också
            time.sleep(args.sleep_ms/1000.0)

    write_csv(args.links, links)
    print(f"[GBLINK] tried={tried}, updated={updated} -> {args.links}")

if __name__ == "__main__":
    main()
