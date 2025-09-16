from __future__ import annotations
from pathlib import Path
import csv
import time
import json
import argparse
from typing import Dict, List, Any, Tuple, Optional

import requests
import pandas as pd
import yaml
import re

# =======================
# Konfig / konstanter
# =======================

# P31 (instance of) filter
ALLOW_P31 = {
    "Q7889",     # video game
    "Q153813",   # video game expansion
    "Q705716",   # video game remake
    # "Q13414952", # demake/port-like (valfri – lämna avkommenterad om du vill vara striktare)
}
DENY_P31 = {
    "Q11424",    # film
    "Q5398426",  # television series
    "Q482994",   # album
    "Q134556",   # novel
    "Q21191270", # soundtrack album
    "Q15265344", # video game series
    "Q17379835", # media franchise
}

ED_PATH = Path("data/outputs/editions.csv")
OUT_DIR = Path("data/outputs/enrichment")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ALIASES_PATH = Path("configs/wikidata_platform_aliases.yaml")

WIKIDATA_SEARCH = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITIES = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"

# Höflig rate limiting så vi inte blir blockerade
REQ_SLEEP = 0.25  # sek mellan requests
UA = "Exjobb-Worko-Wikidata-POC/0.2 (contact: your-email@example.com)"

# =======================
# Hjälpare
# =======================

def load_aliases() -> Dict[str, List[str]]:
    """Läs plattformsalias (för P400-matchning) från YAML."""
    if ALIASES_PATH.exists():
        with open(ALIASES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            clean = {}
            for k, v in data.items():
                if isinstance(v, list):
                    clean[k] = [str(x) for x in v]
                elif isinstance(v, str):
                    clean[k] = [v]
            return clean
    return {}

def _simplify_title(t: str) -> str:
    """Rensa titel: ta bort parenteser/tecken, klipp efter första kolon/streck."""
    s = t.replace("—", "-").replace("–", "-")
    s = re.sub(r"[\(\)\[\]\{\}:;,.!?]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # "Game: Subtitle" -> "Game"
    s = re.split(r"\s[-:]\s", s, maxsplit=1)[0]
    return s

def _wbsearch(title: str, language: str = "en", limit: int = 8) -> list[dict]:
    """Wikidata wbsearchentities."""
    params = {
        "action": "wbsearchentities",
        "search": title,
        "language": language,
        "format": "json",
        "type": "item",
        "limit": str(limit),
    }
    headers = {"User-Agent": UA}
    r = requests.get(WIKIDATA_SEARCH, params=params, headers=headers, timeout=15)
    time.sleep(REQ_SLEEP)
    r.raise_for_status()
    return r.json().get("search", [])

def search_wikidata_title(title: str, limit: int = 8) -> list[dict]:
    """Prova flera språk + förenklad titel tills vi får träffar."""
    if not title or not str(title).strip():
        return []
    langs = ["en", "ja", "sv"]  # prova flera UI-språk i söken
    tries: list[tuple[str, str]] = []

    # 1) exakt titel i alla språk
    for lg in langs:
        tries.append((title, lg))

    # 2) förenklad titel i alla språk
    simp = _simplify_title(title)
    if simp and simp.lower() != title.lower():
        for lg in langs:
            tries.append((simp, lg))

    # Kör i ordning, returnera första set:et som gav träffar
    for text, lg in tries:
        hits = _wbsearch(text, lg, limit)
        if hits:
            return hits
    return []

def fetch_entity(qid: str) -> Dict[str, Any]:
    """Hämta hela entiteten (labels, claims, etc.)."""
    url = WIKIDATA_ENTITIES.format(qid)
    headers = {"User-Agent": UA}
    r = requests.get(url, headers=headers, timeout=20)
    time.sleep(REQ_SLEEP)
    r.raise_for_status()
    data = r.json()
    return data.get("entities", {}).get(qid, {})

def get_label(entity: Dict[str, Any], pref_langs=("en", "sv", "ja")) -> str:
    labels = entity.get("labels", {})
    for lang in pref_langs:
        if lang in labels:
            return labels[lang].get("value", "")
    if labels:
        return next(iter(labels.values())).get("value", "")
    return ""

def claim_values(entity: Dict[str, Any], prop: str) -> List[str]:
    """Extrahera Q-id:n (eller literals) från claims."""
    vals: List[str] = []
    for stmt in entity.get("claims", {}).get(prop, []):
        mainsnak = stmt.get("mainsnak", {})
        datav = mainsnak.get("datavalue", {})
        if not datav:
            continue
        vtype = datav.get("type")
        if vtype == "wikibase-entityid":
            q = datav.get("value", {}).get("id")
            if q:
                vals.append(q)
        elif vtype in ("string", "time", "monolingualtext"):
            vals.append(datav.get("value"))
        # andra typer ignoreras i POC
    return vals

def time_to_date_str(wb_time: Any) -> str:
    """Konvertera Wikidata time value till yyyy-mm-dd (enkel)."""
    if not wb_time:
        return ""
    if isinstance(wb_time, dict) and "time" in wb_time:
        t = wb_time["time"]  # t.ex. "+2013-09-17T00:00:00Z"
    else:
        t = str(wb_time)
    t = t.strip("+")
    return t.split("T")[0]

def labels_for_qids(qids: List[str]) -> Dict[str, str]:
    """Hämta etiketter för många Q-id (loop; duger i PoC)."""
    out: Dict[str, str] = {}
    for q in qids:
        try:
            e = fetch_entity(q)
            out[q] = get_label(e)
        except Exception:
            out[q] = ""
    return out

def platform_labels(entity: Dict[str, Any]) -> List[str]:
    """Hämta plattforms-labels (P400) för entiteten."""
    p_qids = claim_values(entity, "P400")
    if not p_qids:
        return []
    lbls = labels_for_qids(p_qids)
    return [v for v in lbls.values() if v]

def instance_of_qids(entity: dict) -> list[str]:
    """Hämta Q-id för P31 (instance of)."""
    return claim_values(entity, "P31")

def has_allowed_instance(entity: dict) -> bool:
    """Tillåt endast video game-lika entiteter, neka film/album/serie etc."""
    p31s = set(instance_of_qids(entity))
    if not p31s:
        return False
    if p31s & DENY_P31:
        return False
    return bool(p31s & ALLOW_P31)

# =======================
# Matchning / scoring
# =======================

def pick_best_candidate(
    title: str,
    platform_norm: str,
    aliases: Dict[str, List[str]],
    candidates: List[Dict[str, Any]],
) -> Tuple[Optional[str], Dict[str, Any], List[Dict[str, Any]]]:
    """Välj bästa kandidat med regler: P31, titel, plattform."""
    plat_aliases = [a.casefold() for a in aliases.get(platform_norm, [])]
    title_cf = title.casefold()

    inspected: List[Dict[str, Any]] = []
    best: Optional[Tuple[str, Dict[str, Any]]] = None
    best_score = (-1, -1, -1)  # (platform_match 0/1, title_score 0..2, p31_ok 0/1)

    for hit in candidates:
        qid = hit.get("id")
        label = hit.get("label", "") or hit.get("display", {}).get("label", {}).get("value", "")
        desc = hit.get("description", "") or hit.get("display", {}).get("description", {}).get("value", "")

        try:
            ent = fetch_entity(qid)
        except Exception:
            continue

        # P400 (platform labels)
        plats = platform_labels(ent)
        plats_cf = [p.casefold() for p in plats]
        plat_match = 0
        if plat_aliases and plats_cf:
            for a in plat_aliases:
                if any(a == p or a in p for p in plats_cf):
                    plat_match = 1
                    break

        # Titelpoäng
        label_cf = (label or "").casefold()
        if label_cf == title_cf:
            tscore = 2
        elif title_cf in label_cf or label_cf in title_cf:
            tscore = 1
        else:
            tscore = 0

        # P31 filter
        p31_ok = 1 if has_allowed_instance(ent) else 0

        # Bygg score
        score = (plat_match, tscore, p31_ok)

        inspected.append({
            "qid": qid,
            "label": label,
            "description": desc,
            "platform_labels": "; ".join(plats) if plats else "",
            "title_score": tscore,
            "platform_match": plat_match,
            "p31_ok": p31_ok,
            "score_tuple": str(score),
        })

        # Strikt regel:
        # - Om entiteten HAR P400: kräv plattforms-match.
        # - Om entiteten SAKNAR P400: tillåt endast EXAKT titel (tscore==2).
        has_p400 = len(plats_cf) > 0
        if p31_ok == 1 and tscore >= 1 and ((has_p400 and plat_match == 1) or (not has_p400 and tscore == 2)):
            if score > best_score:
                best_score = score
                best = (qid, ent)

    # Fallback: om inget hade p31_ok==1 som kvalade, välj bästa med titel>=1 + plat_match==1
    if not best:
        for hit in candidates:
            qid = hit.get("id")
            label = hit.get("label", "") or hit.get("display", {}).get("label", {}).get("value", "")
            try:
                ent = fetch_entity(qid)
            except Exception:
                continue
            plats = platform_labels(ent)
            plats_cf = [p.casefold() for p in plats]
            plat_match = 1 if any(a == p or a in p for a in [*plat_aliases] for p in plats_cf) else 0
            label_cf = (label or "").casefold()
            tscore = 2 if label_cf == title_cf else (1 if title_cf in label_cf or label_cf in title_cf else 0)
            score = (plat_match, tscore, 0)
            if tscore >= 1 and plat_match == 1:
                if score > best_score:
                    best_score = score
                    best = (qid, ent)

    if best:
        return best[0], best[1], inspected
    return None, {}, inspected

# =======================
# Enrichment
# =======================

def enrich_one(title: str, platform_norm: str, aliases: Dict[str, List[str]]) -> Tuple[Optional[str], Dict[str, Any], List[Dict[str, Any]]]:
    """Sök + hämta bästa entitet."""
    cands = search_wikidata_title(title, limit=8)
    print(f"   · kandidater: {len(cands)}")
    if not cands:
        return None, {}, []
    return pick_best_candidate(title, platform_norm, aliases, cands)

# =======================
# Main
# =======================

def main():
    ap = argparse.ArgumentParser(description="Wikidata enrichment PoC (safe, read-only)")
    ap.add_argument("--in", dest="editions_csv", default=str(ED_PATH), help="Path to editions.csv")
    ap.add_argument("--out", dest="out_csv", default=str(OUT_DIR / "wikidata_enrichment.csv"), help="Output enrichment CSV")
    ap.add_argument("--candidates_out", dest="cand_csv", default=str(OUT_DIR / "wikidata_candidates.csv"), help="Output candidates CSV")
    ap.add_argument("--limit", type=int, default=100, help="Max antal editioner att köra (för snabbtest)")
    ap.add_argument("--filter_title", type=str, default="", help="Kör bara editioner vars titel innehåller denna sträng (case-insensitive)")
    ap.add_argument("--platform_whitelist", type=str, nargs="*", default=[], help="Kör bara för dessa platform_norm-koder (t.ex. SNES SFC MD)")
    args = ap.parse_args()

    # Läs editions
    if not Path(args.editions_csv).exists():
        print(f"❌ Hittar inte {args.editions_csv}")
        return
    ed = pd.read_csv(args.editions_csv, dtype=str).fillna("")
    if args.filter_title:
        f = args.filter_title.casefold()
        ed = ed[ed["title_primary"].astype(str).str.casefold().str.contains(f)]
    if args.platform_whitelist:
        wl = set(args.platform_whitelist)
        ed = ed[ed["platform"].isin(wl)]

    # Ta bara unika editioner (säkerhet) och begränsa
    ed = ed.drop_duplicates(subset=["edition_id"]).reset_index(drop=True)
    if args.limit > 0:
        ed = ed.head(args.limit)

    aliases = load_aliases()

    enrich_rows: List[Dict[str, Any]] = []
    cand_rows: List[Dict[str, Any]] = []

    for i, row in ed.iterrows():
        edition_id = row.get("edition_id", "")
        title = row.get("title_primary", "")
        platform_norm = row.get("platform", "")

        print(f"[{i+1}/{len(ed)}] {title} ({platform_norm}) …")
        try:
            qid, ent, inspected = enrich_one(title, platform_norm, aliases)
        except Exception as e:
            print(f"  ! Fel: {e}")
            qid, ent, inspected = None, {}, []

        # Spara kandidater för transparens
        for c in inspected:
            cand_rows.append({
                "edition_id": edition_id,
                **c
            })

        # Bygg enrichment-rad (även om None)
        if qid and ent:
            # Release date (P577) – ta första
            p577 = claim_values(ent, "P577")
            date = time_to_date_str(p577[0]) if p577 else ""

            # Publisher (P123), Developer (P178), Country (P495), Language (P407)
            pubs_q = claim_values(ent, "P123")
            devs_q = claim_values(ent, "P178")
            ctry_q = claim_values(ent, "P495")
            lang_q = claim_values(ent, "P407")

            labels_map = labels_for_qids(list(set(pubs_q + devs_q + ctry_q + lang_q)))
            pubs = "; ".join([labels_map.get(q, q) for q in pubs_q]) if pubs_q else ""
            devs = "; ".join([labels_map.get(q, q) for q in devs_q]) if devs_q else ""
            ctrs = "; ".join([labels_map.get(q, q) for q in ctry_q]) if ctry_q else ""
            langs = "; ".join([labels_map.get(q, q) for q in lang_q]) if lang_q else ""

            enrich_rows.append({
                "edition_id": edition_id,
                "title_primary": title,
                "platform": platform_norm,
                "wikidata_qid": qid,
                "wikidata_label": get_label(ent),
                "release_date_p577": date,
                "publisher_p123": pubs,
                "developer_p178": devs,
                "country_of_origin_p495": ctrs,
                "languages_p407": langs,
                "platform_labels_p400": "; ".join(platform_labels(ent)),
                "source": "wikidata",
            })
        else:
            enrich_rows.append({
                "edition_id": edition_id,
                "title_primary": title,
                "platform": platform_norm,
                "wikidata_qid": "",
                "wikidata_label": "",
                "release_date_p577": "",
                "publisher_p123": "",
                "developer_p178": "",
                "country_of_origin_p495": "",
                "languages_p407": "",
                "platform_labels_p400": "",
                "source": "wikidata",
            })

    # Skriv ut
    enr_df = pd.DataFrame(enrich_rows)
    cand_df = pd.DataFrame(cand_rows)

    enr_df.to_csv(args.out_csv, index=False, encoding="utf-8")
    cand_df.to_csv(args.cand_csv, index=False, encoding="utf-8")

    print(f"\n✅ Skrev {len(enr_df)} rader → {args.out_csv}")
    print(f"✅ Skrev {len(cand_df)} kandidatrader → {args.cand_csv}")
    print("Klar.")

if __name__ == "__main__":
    main()
