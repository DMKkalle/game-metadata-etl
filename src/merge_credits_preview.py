# File: src/merge_credits_preview.py
# Usage:
#   python .\src\merge_credits_preview.py
#   python .\src\merge_credits_preview.py --limit 10
#   python .\src\merge_credits_preview.py --limit 10 --use-wd
#
# Gör:
# 1) Läser de första N spelen från data/processed/editions_enriched_snes.csv
# 2) Hämtar personer från GiantBomb (gb_people.csv) per edition_id
# 3) Hämtar roller från Wikipedia (infobox) per titel
# 4) (valfritt) Hämtar personroller från Wikidata (composer/producer/director) via SPARQL
# 5) Matchar namn mellan källor och skriver ut en konsolrapport:
#       - GB+Wiki match => confidence=high
#       - GB only       => role=unknown, confidence=medium
#       - Wiki/Wikidata only => confidence=low
#
# Sparar ingenting – endast för handgranskning.

import argparse
import time
import csv
import os
import re
import sys
from collections import defaultdict, Counter

import requests

CSV_EDITIONS = r"data/processed/editions_enriched_snes.csv"
CSV_GB_PEOPLE = r"data/external/giantbomb/gb_people.csv"

WIKI_API = "https://en.wikipedia.org/w/api.php"
WD_SPARQL = "https://query.wikidata.org/sparql"

# --- Hjälpfunktioner ---------------------------------------------------------

def load_editions(limit=None):
    rows = []
    with open(CSV_EDITIONS, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append(r)
            if limit and len(rows) >= limit:
                break
    return rows

def load_gb_people():
    # Förväntar kolumner: edition_id, person_name, gb_game_id, gb_person_id (kan finnas fler)
    if not os.path.exists(CSV_GB_PEOPLE):
        return defaultdict(list)
    out = defaultdict(list)
    with open(CSV_GB_PEOPLE, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            eid = r.get("edition_id") or ""
            name = (r.get("person_name") or "").strip()
            if eid and name:
                out[eid].append(name)
    # unika per edition
    for k, v in out.items():
        uniq = []
        seen = set()
        for n in v:
            key = norm_name(n)
            if key not in seen:
                seen.add(key)
                uniq.append(n)
        out[k] = uniq
    return out

def norm_name(s: str) -> str:
    s = (s or "").strip().lower()
    # ta bort wikilänkar [[Name]] -> Name
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)
    # ta bort extra whitespace
    s = re.sub(r"\s+", " ", s)
    return s

def split_people_field(val: str):
    """
    Delar upp sträng med namn från infoboxfält (hanterar <br />, komma,
    wikilänkar [[...]]). Returnerar rena namn.
    """
    if not val:
        return []
    # ersätt <br> varianter med kommatecken
    x = re.sub(r"<\s*br\s*/?\s*>", ",", val, flags=re.I)
    # ta bort referenser <ref ...>...</ref> och <ref .../>
    x = re.sub(r"<ref[^>]*>.*?</ref>", "", x, flags=re.I|re.S)
    x = re.sub(r"<ref[^>]*/>", "", x, flags=re.I)
    # ta bort mallar {{...}} (enklare variant)
    x = re.sub(r"\{\{[^{}]*\}\}", "", x)
    # dela
    parts = [p.strip(" \t\r\n,;") for p in re.split(r"[;,]", x) if p.strip()]
    # wikilänk [[A|B]] -> B, [[A]] -> A
    out = []
    for p in parts:
        m = re.match(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", p)
        if m:
            out.append(m.group(1).strip())
        else:
            out.append(p)
    # rensa tomma
    out = [o for o in out if o]
    # unika, bevara ordning
    uniq = []
    seen = set()
    for o in out:
        k = norm_name(o)
        if k not in seen:
            seen.add(k)
            uniq.append(o)
    return uniq

# --- Wikipedia: hämta infobox och extrahera roller ---------------------------

INFOBOX_ROLES = [
    # Personcentrerade roller från infobox VG
    "designer",
    "programmer",
    "artist",
    "composer",
    "director",
    "producer",
    # Organisationer också ok, men primärt personer ovan
    "developer",
    "publisher",
]

def wikipedia_get_wikitext(title: str):
    session = requests.Session()
    headers = {
        "User-Agent": "EmbracerThesisBot/1.0 (contact: your-email@example.com)",
        "Accept": "application/json",
    }

    def _get(params, tries=5):
        backoff = 1.0
        for i in range(tries):
            r = session.get(WIKI_API, params=params, headers=headers, timeout=30)
            # mjuk-hantering av rate/forbidden
            if r.status_code in (429, 403, 502, 503, 504):
                time.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
                continue
            r.raise_for_status()
            return r
        # sista försök – låt raise_for_status tala om ev. fel
        r.raise_for_status()
        return r

    # 1) försök direkt på titeln
    params = {
        "action": "parse",
        "page": title,
        "prop": "wikitext",
        "format": "json",
        "redirects": 1,
        "origin": "*",
    }
    r = _get(params)
    j = r.json()
    wikitext = j.get("parse", {}).get("wikitext", {}).get("*")
    if wikitext:
        return wikitext

    # 2) fallback: opensearch för att hitta korrekt sida
    sparams = {
        "action": "opensearch",
        "search": title,
        "limit": 1,
        "namespace": 0,
        "format": "json",
        "origin": "*",
    }
    rs = _get(sparams)
    sj = rs.json()
    if len(sj) >= 2 and sj[1]:
        new_title = sj[1][0]
        params["page"] = new_title
        r2 = _get(params)
        j2 = r2.json()
        return j2.get("parse", {}).get("wikitext", {}).get("*", "")

    return ""

def wikipedia_extract_infobox_roles(wikitext: str):
    """
    Plockar ut roller från {{Infobox video game}} / {{Infobox VG}} block.
    Returnerar lista av (role, [names])
    """
    if not wikitext:
        return []

    # hitta infobox-blocket (enkel, räcker i praktiken för vår test)
    m = re.search(r"\{\{\s*Infobox\s*(?:video game|VG)\b(.*?)\n\}\}", wikitext, flags=re.I | re.S)
    if not m:
        return []

    box = m.group(1)
    results = []
    for role in INFOBOX_ROLES:
        # sök rad som börjar med | role =
        # tillåter mellanrum: "|programmer  = ..." osv
        rx = re.compile(rf"\|\s*{re.escape(role)}\s*=\s*(.+)", flags=re.I)
        mm = rx.search(box)
        if not mm:
            continue
        raw = mm.group(1).strip()
        people = split_people_field(raw)
        if people:
            results.append((role.lower(), people))
    return results

# --- Wikidata: (valfritt) hämta personroller --------------------------------

WD_PERSON_ROLES = {
    "composer": "P86",
    "director": "P57",
    "producer": "P162",
    # Obs: developer (P178) & publisher (P123) kan vara både person/org
}

WD_PLATFORM_SNES = "Q171730"  # Super Nintendo Entertainment System

def wd_find_qid_by_title_and_snes(title: str):
    """
    Hitta spel-QID genom exakt engelskt label-match + plattform SNES (P400).
    Returnerar första QID eller None.
    """
    query = f"""
    SELECT ?game WHERE {{
      ?game rdfs:label "{title}"@en .
      ?game wdt:P31 wd:Q7889 .   # instance of video game
      ?game wdt:P400 wd:{WD_PLATFORM_SNES} .  # platform SNES
    }} LIMIT 1
    """
    r = requests.get(WD_SPARQL, params={"query": query, "format": "json"}, headers={"Accept": "application/sparql-results+json"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    b = j.get("results", {}).get("bindings", [])
    if not b:
        return None
    uri = b[0]["game"]["value"]
    return uri.rsplit("/", 1)[-1]

def wd_fetch_person_roles(qid: str):
    """
    Hämtar personroller (composer, producer, director) från Wikidata för ett spel-QID.
    Returnerar dict: { role -> [names] }
    """
    if not qid:
        return {}
    # Hämta namn för personliga roller
    # Rollen -> property
    chunks = []
    for role, prop in WD_PERSON_ROLES.items():
        chunk = f"""
        OPTIONAL {{
          wd:{qid} wdt:{prop} ?{role} .
          ?{role} rdfs:label ?{role}Label .
          FILTER (lang(?{role}Label) = "en")
        }}
        """
        chunks.append(chunk)
    query = f"""
    SELECT DISTINCT ?composerLabel ?producerLabel ?directorLabel WHERE {{
      {" ".join(chunks)}
    }}
    """
    r = requests.get(WD_SPARQL, params={"query": query, "format": "json"}, headers={"Accept": "application/sparql-results+json"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    out = defaultdict(list)
    for row in j.get("results", {}).get("bindings", []):
        for role in WD_PERSON_ROLES.keys():
            key = role + "Label"
            if key in row and "value" in row[key]:
                name = row[key]["value"].strip()
                if name:
                    out[role].append(name)
    # unika
    for k, v in out.items():
        uniq = []
        seen = set()
        for n in v:
            nn = norm_name(n)
            if nn not in seen:
                seen.add(nn)
                uniq.append(n)
        out[k] = uniq
    return dict(out)

# --- Merge-logik -------------------------------------------------------------

def merge_people(edition_id, title, gb_names, wiki_roles, wd_roles=None):
    """
    gb_names: [str]
    wiki_roles: [(role, [names])]
    wd_roles: {role: [names]} eller None
    Returnerar en lista med poster:
      {
        "name": "...",
        "roles": ["designer", "programmer"],
        "sources": {"gb","wikipedia","wikidata"},
        "confidence": "high|medium|low"
      }
    """
    wiki_map = defaultdict(set)   # name_norm -> set(roles)
    wiki_raw_names = set()

    for role, names in wiki_roles:
        for n in names:
            wiki_raw_names.add(n)
            wiki_map[norm_name(n)].add(role)

    wd_map = defaultdict(set)
    wd_raw_names = set()
    if wd_roles:
        for role, names in wd_roles.items():
            for n in names:
                wd_raw_names.add(n)
                wd_map[norm_name(n)].add(role)

    out = []
    used_wiki = set()
    used_wd = set()

    # 1) börja med GB-namn och hitta match i Wiki/WD
    for gb in gb_names:
        key = norm_name(gb)
        roles = set()
        sources = set(["gb"])
        if key in wiki_map:
            roles |= wiki_map[key]
            sources.add("wikipedia")
            used_wiki.add(key)
        if key in wd_map:
            roles |= wd_map[key]
            sources.add("wikidata")
            used_wd.add(key)

        if roles:
            confidence = "high" if "wikipedia" in sources else "high" if "wikidata" in sources else "medium"
        else:
            confidence = "medium"  # GB-only, ingen roll hittad

        out.append({
            "name": gb,
            "roles": sorted(roles),
            "sources": sorted(sources),
            "confidence": confidence
        })

    # 2) Lägg till namn som endast finns i Wiki
    for n in sorted(wiki_raw_names, key=lambda s: norm_name(s)):
        key = norm_name(n)
        if key in used_wiki:
            continue
        if not any(norm_name(x) == key for x in gb_names):
            out.append({
                "name": n,
                "roles": sorted(wiki_map[key]),
                "sources": ["wikipedia"],
                "confidence": "low"
            })

    # 3) Lägg till namn som endast finns i WD (om de inte redan är täckta)
    for n in sorted(wd_raw_names, key=lambda s: norm_name(s)):
        key = norm_name(n)
        if key in used_wd:
            continue
        if not any(norm_name(x) == key for x in gb_names) and key not in wiki_map:
            out.append({
                "name": n,
                "roles": sorted(wd_map[key]),
                "sources": ["wikidata"],
                "confidence": "low"
            })

    # Sortera utdata: GB först, sen wiki-only, sen wd-only
    def sort_key(item):
        src = ",".join(item["sources"])
        return (0 if "gb" in item["sources"] else 1 if "wikipedia" in item["sources"] else 2, norm_name(item["name"]))
    out.sort(key=sort_key)
    return out

def print_report(edition_id, title, people_rows):
    print("=" * 70)
    print(f"edition_id : {edition_id}")
    print(f"title      : {title}\n")
    if not people_rows:
        print("No people found.")
        return

    # Grupp efter confidence för snabb överblick
    groups = defaultdict(list)
    for r in people_rows:
        groups[r["confidence"]].append(r)

    order = ["high", "medium", "low"]
    for lvl in order:
        if lvl not in groups:
            continue
        print(f"[{lvl.upper()}]")
        for r in groups[lvl]:
            roles = "; ".join(r["roles"]) if r["roles"] else "(unknown)"
            sources = ", ".join(r["sources"])
            print(f"  - {r['name']}  | roles: {roles}  | sources: {sources}")
        print("")

# --- main --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5, help="Antal spel att förhandsgranska")
    ap.add_argument("--use-wd", action="store_true", help="Hämta även personroller (composer/producer/director) från Wikidata")
    args = ap.parse_args()

    editions = load_editions(limit=args.limit)
    gb_people = load_gb_people()

    for ed in editions:
        eid = ed.get("edition_id") or ""
        title = (ed.get("title_primary") or "").strip()
        if not title:
            continue

        gb_names = gb_people.get(eid, [])

        # Wikipedia
        wikitext = wikipedia_get_wikitext(title)
        wiki_roles = wikipedia_extract_infobox_roles(wikitext)

        # Wikidata (valfritt)
        wd_roles = {}
        if args.use_wd:
            qid = wd_find_qid_by_title_and_snes(title)
            if qid:
                wd_roles = wd_fetch_person_roles(qid)

        merged = merge_people(eid, title, gb_names, wiki_roles, wd_roles)
        print_report(eid, title, merged)

    print("\nDone. (No files written)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
