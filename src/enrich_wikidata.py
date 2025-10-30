# src/enrich_wikidata.py
from __future__ import annotations
from pathlib import Path
import time
import argparse
from typing import Dict, List, Any, Tuple, Optional
import re
import requests
import pandas as pd
import yaml
import unicodedata

# ------------------- Paths & constants -------------------
ED_PATH = Path("data/outputs/editions.csv")
ITEMS_TO_ED = Path("data/outputs/items_to_editions.csv")
OBJECTS_EXPANDED = Path("data/outputs/objects_expanded.csv")

OUT_DIR = Path("data/outputs/enrichment")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ALIASES_PATH = Path("configs/wikidata_platform_aliases.yaml")

WIKIDATA_SEARCH = "https://www.wikidata.org/w/api.php"
WIKIDATA_ENTITIES = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"

# Artigt mot Wikidata
REQ_SLEEP = 0.25
UA = "Exjobb-Worko-Wikidata-POC/0.3 (contact: you@example.com)"

# Instance-of filter (P31)
ALLOW_P31 = {  # tillåt
    "Q7889",     # video game
    "Q153813",   # video game expansion
    "Q705716",   # video game remake
}
DENY_P31 = {   # blocka
    "Q11424",    # film
    "Q5398426",  # TV series
    "Q482994",   # album
    "Q134556",   # novel
    "Q21191270", # soundtrack album
    "Q15265344", # video game series
    "Q17379835", # media franchise
}

# ------------------- Utilities -------------------
def normalize_spaces(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u3000", " ")
    for ch in ["・", "･", "•", "‧"]:
        s = s.replace(ch, " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def normalize_title_variants(title: str) -> list[str]:
    base = normalize_spaces(title)
    variants = {base}
    variants.add(base.replace("×", "x").replace("✕", "x").replace("✖", "x"))
    variants.add(re.sub(r"[:;,\-–—]+", " ", base))
    variants.add(re.sub(r"[!?。！．｡]+$", "", base).strip())
    variants.add(re.sub(r"[^0-9A-Za-z\u3040-\u30FF\u4E00-\u9FFF\s]", " ", base))
    variants = {normalize_spaces(v) for v in variants}
    return [v for v in variants if v]

def load_aliases() -> Dict[str, List[str]]:
    if ALIASES_PATH.exists():
        with open(ALIASES_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        clean = {}
        for k, v in raw.items():
            if isinstance(v, list):
                clean[k] = [str(x) for x in v]
            elif isinstance(v, str):
                clean[k] = [v]
        return clean
    # Minimal fallback
    return {
        "SNES": ["Super Nintendo Entertainment System", "Super NES", "Nintendo Super NES"],
        "SFC":  ["Super Famicom", "Nintendo Super Famicom"],
        "MD":   ["Sega Mega Drive"],
        "GEN":  ["Sega Genesis"],
        "NEO-AES": ["Neo Geo AES", "Neo Geo"],
        "NEO-MVS": ["Neo Geo MVS", "Neo Geo"],
    }

def _wbsearch(q: str, language: str = "en", limit: int = 15) -> list[dict]:
    params = {
        "action": "wbsearchentities",
        "search": q,
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

def _simplify_title(t: str) -> str:
    s = t.replace("—", "-").replace("–", "-")
    s = re.sub(r"[()\[\]\{\}:;,.!?]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.split(r"\s[-:]\s", s, maxsplit=1)[0]
    return s

def _title_variants(title: str) -> list[str]:
    variants = set()
    t = (title or "").strip()
    if not t:
        return []
    variants.add(t)
    variants.add(t.replace("×", "x"))
    variants.add(t.replace("x", "×"))
    variants.add(re.sub(r"(?i)\bheno\b", "e no", t))
    variants.add(re.sub(r"(?i)\s+he$", " e", t))
    t2 = t.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    variants.add(t2)
    base = list(variants)
    for v in base:
        variants.add(_simplify_title(v))
    out = [v for v in variants if v and v != title]
    out.sort(key=len, reverse=True)
    return [title] + out

def search_wikidata_title(title: str, limit: int = 15) -> List[Dict[str, Any]]:
    if not title or not title.strip():
        return []
    languages = ["en", "ja", "sv"]
    variants = normalize_title_variants(title)
    headers = {"User-Agent": UA}
    seen_ids = set()
    results: List[Dict[str, Any]] = []
    for lang in languages:
        for q in variants:
            params = {
                "action": "wbsearchentities",
                "search": q,
                "language": lang,
                "format": "json",
                "type": "item",
                "limit": str(limit),
            }
            try:
                r = requests.get(WIKIDATA_SEARCH, params=params, headers=headers, timeout=15)
                time.sleep(REQ_SLEEP)
                r.raise_for_status()
                data = r.json()
                for hit in data.get("search", []):
                    qid = hit.get("id")
                    if qid and qid not in seen_ids:
                        seen_ids.add(qid)
                        results.append(hit)
            except Exception:
                continue
    return results

def fetch_entity(qid: str) -> Dict[str, Any]:
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
    return next(iter(labels.values())).get("value", "") if labels else ""

def claim_values(entity: Dict[str, Any], prop: str) -> List[str]:
    vals = []
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
    return vals

def time_to_date_str(wb_time: Any) -> str:
    if not wb_time:
        return ""
    if isinstance(wb_time, dict) and "time" in wb_time:
        t = wb_time["time"]
    else:
        t = str(wb_time)
    t = t.strip("+")
    return t.split("T")[0]

def labels_for_qids(qids: List[str]) -> Dict[str, str]:
    out = {}
    for q in qids:
        try:
            e = fetch_entity(q)
            out[q] = get_label(e)
        except Exception:
            out[q] = ""
    return out

def platform_labels(entity: Dict[str, Any]) -> List[str]:
    p_qids = claim_values(entity, "P400")
    if not p_qids:
        return []
    lbls = labels_for_qids(p_qids)
    return [v for v in lbls.values() if v]

def instance_of_qids(entity: dict) -> list[str]:
    return claim_values(entity, "P31")

def has_allowed_instance(entity: dict) -> bool:
    p31s = set(instance_of_qids(entity))
    if not p31s:
        return False
    if p31s & DENY_P31:
        return False
    return bool(p31s & ALLOW_P31)

# ------- NEW: work with statements + qualifiers -------
def claim_statements(entity: dict, prop: str) -> list[dict]:
    """Returnera råa statements (inkl. kvalifikatorer) för en property."""
    return entity.get("claims", {}).get(prop, []) or []

def statement_values_with_qualifiers(stmt: dict) -> tuple[Optional[str], dict[str, list[str]]]:
    """Extrahera (value_qid_or_literal, qualifiers_map_qidlist)."""
    mainsnak = stmt.get("mainsnak", {})
    v = mainsnak.get("datavalue")
    if not v:
        return None, {}
    vtype = v.get("type")
    if vtype == "wikibase-entityid":
        value = v["value"]["id"]
    elif vtype in ("string", "time", "monolingualtext"):
        value = v["value"]
    else:
        value = None

    quals: dict[str, list[str]] = {}
    for qprop, lst in (stmt.get("qualifiers") or {}).items():
        ids: list[str] = []
        for qsnak in lst:
            dv = qsnak.get("datavalue")
            if not dv:
                continue
            if dv.get("type") == "wikibase-entityid":
                ids.append(dv["value"]["id"])
            else:
                val = dv.get("value")
                if isinstance(val, str):
                    ids.append(val)
        if ids:
            quals[qprop] = ids
    return value, quals

def label_map_for_qids(qids: list[str]) -> dict[str, str]:
    qids = [q for q in set(qids or []) if isinstance(q, str)]
    out: dict[str, str] = {}
    for q in qids:
        try:
            e = fetch_entity(q)
            out[q] = get_label(e)
        except Exception:
            out[q] = ""
    return out

def platform_match_qids(qual_plat_qids: list[str], aliases: dict[str, list[str]], platform_norm: str) -> bool:
    """Matcha P400-kvalifikatorns etiketter mot våra alias för editionens platform_norm."""
    if not qual_plat_qids:
        return False
    labels = []
    for q in qual_plat_qids:
        try:
            labels.append(get_label(fetch_entity(q)))
        except Exception:
            labels.append("")
    alias_cf = [a.casefold() for a in aliases.get(platform_norm, [])]
    for lbl in labels:
        lcf = (lbl or "").casefold()
        if any(a == lcf or a in lcf for a in alias_cf):
            return True
    return False

def vals_per_platform(entity: dict, prop: str, aliases: dict, platform_norm: str) -> tuple[list[str], list[str]]:
    """
    Returnera (vals_for_platform_labels, vals_all_labels).
    Matchar P400-kvalifikatorn mot alias för platform_norm.
    """
    stmts = claim_statements(entity, prop)
    q_all: list[str] = []
    q_for_plat: list[str] = []

    for stmt in stmts:
        val, quals = statement_values_with_qualifiers(stmt)
        if isinstance(val, str) and val.startswith("Q"):
            q_all.append(val)
            q_plats = quals.get("P400", [])
            if q_plats and platform_match_qids(q_plats, aliases, platform_norm):
                q_for_plat.append(val)

    lbl_all = label_map_for_qids(q_all)
    lbl_for = label_map_for_qids(q_for_plat)
    vals_for = [lbl_for.get(q, "") for q in q_for_plat if lbl_for.get(q, "")]
    vals_all = [lbl_all.get(q, "") for q in q_all if lbl_all.get(q, "")]
    return vals_for, vals_all

# ------------------- Candidate picking -------------------
def pick_best_candidate(
    title: str,
    platform_norm: str,
    aliases: Dict[str, List[str]],
    candidates: List[Dict[str, Any]],
) -> Tuple[Optional[str], Dict[str, Any], List[Dict[str, Any]]]:
    plat_aliases = [a.casefold() for a in aliases.get(platform_norm, [])]
    title_cf = title.casefold()

    inspected = []
    best = None
    best_score = (-1, -1, -1)  # (plat_match, title_score, p31_ok)

    for hit in candidates:
        qid = hit.get("id")
        label = hit.get("label", "") or hit.get("display", {}).get("label", {}).get("value", "")
        desc = hit.get("description", "") or hit.get("display", {}).get("description", {}).get("value", "")

        try:
            ent = fetch_entity(qid)
        except Exception:
            continue

        plats = platform_labels(ent)
        plats_cf = [p.casefold() for p in plats]

        plat_match = 0
        if plat_aliases and plats_cf:
            for a in plat_aliases:
                if any(a == p or a in p for p in plats_cf):
                    plat_match = 1
                    break

        label_cf = (label or "").casefold()
        tscore = 2 if label_cf == title_cf else (1 if (title_cf in label_cf or label_cf in title_cf) else 0)
        p31_ok = 1 if has_allowed_instance(ent) else 0
        has_p400 = len(plats_cf) > 0

        ok = p31_ok == 1 and tscore >= 1 and ((has_p400 and plat_match == 1) or (not has_p400 and tscore == 2))
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

        if ok and score > best_score:
            best_score = score
            best = (qid, ent)

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
            plat_aliases = [a.casefold() for a in aliases.get(platform_norm, [])]
            plat_match = 1 if any(a == p or a in p for a in plat_aliases for p in plats_cf) else 0
            label_cf = (label or "").casefold()
            tscore = 2 if label_cf == title_cf else (1 if title_cf in label_cf or label_cf in title_cf else 0)
            score = (plat_match, tscore, 0)
            if tscore >= 1 and plat_match == 1 and score > best_score:
                best_score = score
                best = (qid, ent)

    if best:
        return best[0], best[1], inspected
    return None, {}, inspected

def enrich_one(title: str, platform_norm: str, aliases: Dict[str, List[str]]) -> Tuple[Optional[str], Dict[str, Any], List[Dict[str, Any]]]:
    cands = search_wikidata_title(title, limit=15)
    if not cands:
        return None, {}, []
    return pick_best_candidate(title, platform_norm, aliases, cands)

# ------------------- Extra titles (alt_titles) -------------------
def split_multi(val: str | None, seps=("|",";")) -> list[str]:
    if not val or pd.isna(val):
        return []
    s = str(val)
    for d in seps:
        s = s.replace(d, "|")
    return [x.strip() for x in s.split("|") if x.strip()]

def collect_extra_titles(editions_df: pd.DataFrame) -> dict[str, list[str]]:
    extra: dict[str, list[str]] = {eid: [] for eid in editions_df["edition_id"].unique()}
    if not (ITEMS_TO_ED.exists() and OBJECTS_EXPANDED.exists()):
        return extra

    items = pd.read_csv(ITEMS_TO_ED, dtype=str).fillna("")
    objs = pd.read_csv(OBJECTS_EXPANDED, dtype=str).fillna("")

    objs = objs.loc[:, [c for c in ["object_id", "title_primary", "alt_titles"] if c in objs.columns]]
    items = items.loc[:, [c for c in ["object_number", "edition_id"] if c in items.columns]]

    merged = items.merge(objs, left_on="object_number", right_on="object_id", how="left")
    for eid, grp in merged.groupby("edition_id"):
        titles = set()
        for _, r in grp.iterrows():
            t1 = r.get("title_primary", "")
            if t1:
                titles.add(t1)
            for alt in split_multi(r.get("alt_titles", "")):
                titles.add(alt)
        base_title = editions_df.loc[editions_df["edition_id"] == eid, "title_primary"]
        if not base_title.empty:
            titles.discard(base_title.iloc[0])
        extra[eid] = sorted(titles)[:8]
    return extra

# ------------------- Main -------------------
def main():
    ap = argparse.ArgumentParser(description="Wikidata enrichment PoC (reads qualifiers for platform/region)")
    ap.add_argument("--in", dest="editions_csv", default=str(ED_PATH), help="Path to editions.csv")
    ap.add_argument("--out", dest="out_csv", default=str(OUT_DIR / "wikidata_enrichment.csv"), help="Output enrichment CSV")
    ap.add_argument("--candidates_out", dest="cand_csv", default=str(OUT_DIR / "wikidata_candidates.csv"), help="Output candidates CSV")
    ap.add_argument("--limit", type=int, default=100, help="Max editioner att köra (för snabbtest)")
    ap.add_argument("--filter_title", type=str, default="", help="Kör bara editioner vars titel innehåller denna sträng (case-insensitive)")
    ap.add_argument("--platform_whitelist", type=str, nargs="*", default=[], help="Kör bara för dessa platform-koder (t.ex. SNES SFC MD)")
    args = ap.parse_args()

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

    ed = ed.drop_duplicates(subset=["edition_id"]).reset_index(drop=True)
    if args.limit > 0:
        ed = ed.head(args.limit)

    eid_to_extra = collect_extra_titles(ed)
    aliases = load_aliases()
    enrich_rows: list[dict] = []
    cand_rows: list[dict] = []

    for i, row in ed.iterrows():
        edition_id = row.get("edition_id", "")
        title = row.get("title_primary", "") or ""
        platform_norm = row.get("platform", "") or ""

        search_titles = [title] + eid_to_extra.get(edition_id, [])
        found_qid = None
        found_ent: Dict[str, Any] = {}
        inspected_all: list[dict] = []

        print(f"[{i+1}/{len(ed)}] {title} ({platform_norm}) …")

        for attempt, t in enumerate(search_titles, start=1):
            cands = search_wikidata_title(t, limit=15)
            print(f"   · kandidater (variant {attempt}/{len(search_titles)}): {len(cands)}")
            if not cands:
                continue
            qid, ent, inspected = pick_best_candidate(t, platform_norm, aliases, cands)
            inspected_all.extend(inspected)
            if qid and ent:
                found_qid, found_ent = qid, ent
                break

        for c in inspected_all:
            cand_rows.append({"edition_id": edition_id, **c})

        if found_qid and found_ent:
            # ---- PLATFORM-SPECIFIC RELEASE (P577) + REGION (P291) ----
            date_chosen = ""
            region_lbls = ""
            p577_stmts = claim_statements(found_ent, "P577")
            regions_q_all: list[str] = []
            platform_date_candidates: list[tuple[str, list[str]]] = []

            for stmt in p577_stmts:
                val, quals = statement_values_with_qualifiers(stmt)
                date_str = time_to_date_str(val)
                q_plats = quals.get("P400", [])
                q_region = quals.get("P291", [])
                if q_region:
                    regions_q_all.extend(q_region)
                if q_plats and platform_match_qids(q_plats, aliases, platform_norm):
                    platform_date_candidates.append((date_str, q_region))

            if platform_date_candidates:
                date_chosen, region_q = platform_date_candidates[0]
                region_lbls = "; ".join(label_map_for_qids(region_q).values()) if region_q else ""
            else:
                all_dates = [time_to_date_str(statement_values_with_qualifiers(s)[0]) for s in p577_stmts]
                all_dates = [d for d in all_dates if d]
                date_chosen = sorted(all_dates)[0] if all_dates else ""
                region_lbls = "; ".join(label_map_for_qids(list(set(regions_q_all))).values()) if regions_q_all else ""

            # ---- DEVELOPERS/PUBLISHERS per platform + all ----
            dev_for, dev_all = vals_per_platform(found_ent, "P178", aliases, platform_norm)
            pub_for, pub_all = vals_per_platform(found_ent, "P123", aliases, platform_norm)

            dev_for_str = "; ".join(dev_for) if dev_for else ""
            dev_all_str = "; ".join(dev_all) if dev_all else ""
            pub_for_str = "; ".join(pub_for) if pub_for else ""
            pub_all_str = "; ".join(pub_all) if pub_all else ""

            # Legacy-kompatibla fält (fyll med for_platform om möjligt, annars all)
            developer_legacy = dev_for_str if dev_for_str else dev_all_str
            publisher_legacy = pub_for_str if pub_for_str else pub_all_str

            enrich_rows.append({
                "edition_id": edition_id,
                "title_primary": title,
                "platform": platform_norm,
                "wikidata_qid": found_qid,
                "wikidata_label": get_label(found_ent),
                "release_date_p577": date_chosen,
                "release_regions_p291": region_lbls,
                "publisher_p123_for_platform": pub_for_str,
                "publisher_p123_all": pub_all_str,
                "publisher_p123": publisher_legacy,          # legacy
                "developer_p178_for_platform": dev_for_str,
                "developer_p178_all": dev_all_str,
                "developer_p178": developer_legacy,          # legacy
                "country_of_origin_p495": "; ".join(labels_for_qids(claim_values(found_ent, "P495")).values()),
                "languages_p407": "; ".join(labels_for_qids(claim_values(found_ent, "P407")).values()),
                "platform_labels_p400": "; ".join(platform_labels(found_ent)),
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
                "release_regions_p291": "",
                "publisher_p123_for_platform": "",
                "publisher_p123_all": "",
                "publisher_p123": "",
                "developer_p178_for_platform": "",
                "developer_p178_all": "",
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

    # Liten rapport
    hits = (enr_df["wikidata_qid"] != "").sum()
    total = len(enr_df)
    print(f"\n✅ Skrev {total} rader → {args.out_csv}")
    print(f"✅ Skrev {len(cand_df)} kandidatrader → {args.cand_csv}")
    print(f"🎯 Match rate: {hits}/{total} ({hits/total:.1%})")

if __name__ == "__main__":
    main()
