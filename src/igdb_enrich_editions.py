# src/igdb_enrich_editions.py
from __future__ import annotations
import re
import csv
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime, timezone, date

import pandas as pd

from igdb_client import IGDBClient

ED_PATH = Path("data/outputs/editions.csv")
OUT_DIR = Path("data/outputs/enrichment")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "igdb_enrichment.csv"

# Er plattformskod -> namnalias som IGDB använder
PLATFORM_ALIASES: Dict[str, List[str]] = {
    "SNES": ["Super Nintendo Entertainment System", "Super NES", "Nintendo Super NES"],
    "SFC":  ["Super Famicom", "Nintendo Super Famicom", "Super Nintendo Entertainment System"],
    "GEN":  ["Sega Genesis", "Mega Drive"],
    "MD":   ["Sega Mega Drive", "Mega Drive"],
    "NES":  ["Nintendo Entertainment System"],
    "GB":   ["Game Boy"],
    "GBC":  ["Game Boy Color"],
    "GBA":  ["Game Boy Advance"],
    "N64":  ["Nintendo 64"],
    "PS1":  ["PlayStation"],
    "PS2":  ["PlayStation 2"],
    "PS3":  ["PlayStation 3"],
    "PS4":  ["PlayStation 4"],
    "PS5":  ["PlayStation 5"],
    "SAT":  ["SEGA Saturn"],
    "DC":   ["Dreamcast"],
    "PC":   ["PC (Microsoft Windows)", "Windows"],
}

# ---------- små hjälpare ----------
def norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("×", "x").replace("✕", "x").replace("✖", "x")
    return s.lower()

def title_score(query: str, candidate_name: str) -> int:
    """2 = exakt (case-insensitive), 1 = substring, 0 = annan."""
    q = norm(query)
    c = norm(candidate_name)
    if q and c and q == c:
        return 2
    if q and (q in c or c in q):
        return 1
    return 0

def platform_match(platform_norm: str, igdb_platforms: List[Dict[str, Any]]) -> bool:
    aliases = [a.lower() for a in PLATFORM_ALIASES.get(platform_norm, [])]
    if not aliases:
        return True  # tolerant om vi saknar alias
    names = [norm(p.get("name", "")) for p in (igdb_platforms or [])]
    return any(any(a in n or n in a for n in names) for a in aliases)

def pick_best_hit(title: str, platform_norm_code: str, hits: List[Dict[str, Any]]) -> Tuple[Dict[str, Any] | None, str]:
    """
    Välj bästa IGDB-träff: prioritera plattforms-match, sedan titelträff, sedan rating.
    Returnerar (hit, confidence_str).
    """
    scored: List[Tuple[int, int, float, int]] = []  # (plat_match, title_score, rating, index)
    for idx, h in enumerate(hits):
        ts = title_score(title, h.get("name", ""))
        pm = 1 if platform_match(platform_norm_code, h.get("platforms", [])) else 0
        rating = float(h.get("aggregated_rating") or 0.0)
        scored.append((pm, ts, rating, idx))
    if not scored:
        return None, "0/0"
    pm, ts, rt, ix = max(scored)
    return hits[ix], f"{pm}/{ts}"

def join_names(items, key="name") -> str:
    return "; ".join(i.get(key) for i in (items or []) if i and i.get(key))

def dev_pub_for_platform(details: Dict[str, Any], platform_norm_code: str) -> Tuple[str, str]:
    """
    IGDB har dev/pub via involved_companies (inte per plattform).
    Pragmatisk regel:
      - Om spelet har vår plattform i 'platforms' -> ta alla dev/pub.
      - Annars lämna tomt (plattform mismatch).
    """
    has_platform = platform_match(platform_norm_code, details.get("platforms", []))
    devs, pubs = [], []
    for ic in details.get("involved_companies", []) or []:
        name = (ic.get("company") or {}).get("name", "")
        if not name:
            continue
        if ic.get("developer"):
            devs.append(name)
        if ic.get("publisher"):
            pubs.append(name)
    devs = "; ".join(sorted(set(devs))) if has_platform else ""
    pubs = "; ".join(sorted(set(pubs))) if has_platform else ""
    return devs, pubs

def parse_human_date_key(human: str) -> tuple:
    """
    Ger (YYYY, MM, DD, is_tbd) för sortering.
    - Fångar YYYY-MM(-DD), eller "Aug 1993" -> (1993,08,01)
    - Annars TBD sist.
    """
    if not human:
        return (9999, 12, 31, 1)
    m = re.search(r"\b(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?\b", human)
    if m:
        y = int(m.group(1)); mm = int(m.group(2) or 1); dd = int(m.group(3) or 1)
        return (y, mm, dd, 0)
    m2 = re.search(r"\b([A-Za-z]{3,9})\s+(\d{4})\b", human)
    if m2:
        from calendar import month_abbr
        mon = m2.group(1)[:3].title()
        y = int(m2.group(2))
        try:
            mm = list(month_abbr).index(mon)
        except ValueError:
            mm = 1
        return (y, mm, 1, 0)
    return (9999, 12, 31, 1)

def cover_url_from_image_id(image_id: str | None) -> str:
    if not image_id:
        return ""
    return f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"

# ---------- datum/region-hjälpare ----------
def _ymd(s: str) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def _ts_to_ymd_str(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""

def _human_to_ymd_str(human: str) -> str:
    if not human:
        return ""
    # YYYY, YYYY-MM, YYYY-MM-DD
    m = re.search(r"\b(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?\b", human)
    if m:
        y = m.group(1); mo = m.group(2) or "01"; d = m.group(3) or "01"
        return f"{y}-{mo}-{d}"
    # "Aug 1993" -> 1993-08-01
    m2 = re.search(r"\b([A-Za-z]{3,9})\s+(\d{4})\b", human)
    if m2:
        from calendar import month_abbr
        mon = m2.group(1)[:3].title()
        y = int(m2.group(2))
        try:
            mm = list(month_abbr).index(mon)
        except ValueError:
            mm = 1
        return f"{y}-{mm:02d}-01"
    return ""

# ---------- kärnlogik ----------
def release_for_platform(details: Dict[str, Any], platform_norm_code: str, regions_map: Dict[int, str]) -> Tuple[str, str]:
    """
    Välj bästa release-datum för vår plattform.
    - Prioritet: release_dates där platform.name matchar våra alias.
    - Datum: försök 'date' (ts) -> 'YYYY-MM-DD'; annars parsea 'human'.
    - Region: saknas region på vald rad? Hitta närmaste rad (samma plattform) som *har* region och låna den.
    """
    aliases = [a.lower() for a in PLATFORM_ALIASES.get(platform_norm_code, [])]
    candidates = []
    for rd in details.get("release_dates", []) or []:
        plat = (rd.get("platform") or {}).get("name", "") or ""
        if not plat:
            continue
        if aliases and not any(a in plat.lower() or plat.lower() in a for a in aliases):
            continue

        date_ymd = _ts_to_ymd_str(rd.get("date")) or _human_to_ymd_str(rd.get("human") or "")
        region_name = regions_map.get(rd.get("region"), "") if rd.get("region") else ""
        candidates.append({
            "date_ymd": date_ymd,
            "region": region_name,
            "plat": plat,
            "orig": rd,
        })

    # välj första som har datum (äldst först)
    candidates.sort(key=lambda c: (c["date_ymd"] or "9999-12-31"))
    best = next((c for c in candidates if c["date_ymd"]), None)
    if not best:
        return "", ""

    # region fallback: om best saknar region, hitta *närmast datum* bland samma plattform som har region
    if not best["region"]:
        target = _ymd(best["date_ymd"])
        if target:
            with_region = [c for c in candidates if c["region"] and c["date_ymd"]]
            if with_region:
                with_region.sort(key=lambda c: abs((_ymd(c["date_ymd"]) - target).days))
                best_region = with_region[0]["region"]
                return best["date_ymd"], best_region

    return best["date_ymd"], best["region"]

def flatten_all_release_rows(details: Dict[str, Any], regions_map: Dict[int, str], platform_norm_code: str) -> str:
    """
    Bygger en snygg, deduplicerad, sorterad lista över alla releases.
    Prioriterar rader för den aktuella plattformen överst.
    """
    rows = []
    for rd in details.get("release_dates", []) or []:
        human = rd.get("human") or ""
        rid = rd.get("region")
        rname = regions_map.get(rid, "") if rid else ""
        plat = (rd.get("platform") or {}).get("name", "") or ""
        if not (human or rname or plat):
            continue
        parts = []
        if human: parts.append(human)
        if rname: parts.append(f"[{rname}]")
        if plat:  parts.append(f"<{plat}>")
        item_str = " ".join(parts)
        rows.append((item_str, parse_human_date_key(human), norm(plat)))

    # dedupe
    seen = set()
    uniq = []
    for s, key, plat_lc in rows:
        if s not in seen:
            seen.add(s)
            uniq.append((s, key, plat_lc))

    # sortera på datum (äldst först), därefter strängen
    uniq.sort(key=lambda x: (x[1], x[0]))

    # flytta vår plattform överst
    aliases = [a.lower() for a in PLATFORM_ALIASES.get(platform_norm_code, [])]
    def is_our_plat(plat_lc: str) -> bool:
        return any(a in plat_lc or plat_lc in a for a in aliases) if aliases else False

    ours   = [u for u in uniq if is_our_plat(u[2])]
    others = [u for u in uniq if not is_our_plat(u[2])]
    ordered = ours + others

    return " | ".join(u[0] for u in ordered)

def generate_title_variants(title: str) -> List[str]:
    if not title:
        return []
    base = title.strip()
    variants = set()
    variants.add(base)
    variants.add(base.replace("×", "x").replace("✕", "x").replace("✖", "x"))

    # ta bort skiljetecken
    no_punct = re.sub(r"[(){}\[\]:;,.!?]", " ", base)
    variants.add(re.sub(r"\s+", " ", no_punct).strip())

    # korta före kolon/streck (”Game: Subtitle” -> ”Game”)
    short1 = re.split(r"\s*[-–—:]\s*", base, maxsplit=1)[0]
    variants.add(short1.strip())

    # komprimerad (alfa-num + JP tecken + mellanslag)
    compact = re.sub(r"[^0-9A-Za-z\u3040-\u30FF\u4E00-\u9FFF\s]", " ", base)
    variants.add(re.sub(r"\s+", " ", compact).strip())

    out = [v for v in variants if v and v != title]
    out.sort(key=len, reverse=True)  # längsta först
    return out[:8]

# ---------- CSV-utils ----------
def write_rows(path: Path, header: List[str], rows: List[List[Any]]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

# ---------- main ----------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="IGDB enrichment for editions.csv (non-invasive)")
    ap.add_argument("--input", default=str(ED_PATH), help="Path to editions.csv")
    ap.add_argument("--output", default=str(OUT_CSV), help="Output CSV path")
    ap.add_argument("--limit", type=int, default=50, help="Max antal editioner att köra (för snabbtest)")
    ap.add_argument("--per_title_limit", type=int, default=5, help="Hur många IGDB-träffar att hämta per titel")
    ap.add_argument("--platform_whitelist", nargs="*", default=[], help="Kör bara för dessa platform-koder (t.ex. SNES SFC)")
    args = ap.parse_args()

    df = pd.read_csv(args.input, dtype=str).fillna("")
    df = df.drop_duplicates(subset=["edition_id"]).reset_index(drop=True)
    if args.platform_whitelist:
        wl = set(args.platform_whitelist)
        df = df[df["platform"].isin(wl)]
    if args.limit > 0:
        df = df.head(args.limit)

    client = IGDBClient()
    regions_map = client.regions_map()

    header = [
        "edition_id","title_primary","platform",
        "igdb_id","igdb_name","genres",
        "developers_for_platform","publishers_for_platform",
        "release_date_for_platform","region_for_platform",
        "platforms_all","release_dates_all",
        "cover_url","confidence","source"
    ]
    rows_out: List[List[Any]] = []

    for i, r in df.iterrows():
        eid = r.get("edition_id", "")
        title = r.get("title_primary", "")
        plat = r.get("platform", "")
        print(f"[{i+1}/{len(df)}] {title} ({plat}) …")

        # 1) sök kandidater (pass 1)
        hits = client.search_games_basic(title, limit=args.per_title_limit) or []
        pick, conf = (None, "0/0")
        if hits:
            pick, conf = pick_best_hit(title, plat, hits)

        # 2) extra sökpass om låg träff (ingen pick eller låg confidence)
        low_conf = conf in {"0/0", "0/1"}
        if not pick or low_conf:
            for v in generate_title_variants(title):
                hits2 = client.search_games_basic(v, limit=args.per_title_limit) or []
                if not hits2:
                    continue
                pick2, conf2 = pick_best_hit(title, plat, hits2)  # bedöm mot originaltitel + plattform
                if pick2 and conf2 not in {"0/0"}:
                    pick, conf = pick2, conf2
                    break

        if not pick:
            rows_out.append([eid, title, plat, "", "", "", "", "", "", "", "", "", "", "0/0", "igdb"])
            continue

        # 3) hämta detaljer
        details_list = client.game_details(pick["id"]) or []
        if not details_list:
            rows_out.append([eid, title, plat, "", "", "", "", "", "", "", "", "", "", conf, "igdb"])
            continue
        details = details_list[0]

        # 4) extrahera fält
        igdb_id = details.get("id", "")
        igdb_name = details.get("name", "")
        genres = join_names(details.get("genres", []))

        devs, pubs = dev_pub_for_platform(details, plat)

        # datum/region (endast om plattformen matchar)
        date_ymd, region_name = ("", "")
        if platform_match(plat, details.get("platforms", [])):
            date_ymd, region_name = release_for_platform(details, plat, regions_map)

        platforms_all = join_names(details.get("platforms", []))
        release_all = flatten_all_release_rows(details, regions_map, plat)

        image_id = (details.get("cover") or {}).get("image_id")
        cover_url = cover_url_from_image_id(image_id)

        rows_out.append([
            eid, title, plat,
            igdb_id, igdb_name, genres,
            devs, pubs,
            date_ymd, region_name,
            platforms_all, release_all,
            cover_url, conf, "igdb"
        ])

    write_rows(Path(args.output), header, rows_out)
    print(f"✅ Skrev {len(rows_out)} rader → {args.output}")

if __name__ == "__main__":
    main()
