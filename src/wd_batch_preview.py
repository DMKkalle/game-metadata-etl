import csv
import requests

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "Exjobb-Embracer-Research/0.1 (contact: dmkk@karlstad-university.example)"
}

INPUT_CSV = "data/processed/editions_enriched_snes.csv"
MAX_ROWS = 20  # vi testar på 20 första, inte allt

CREDIT_PROPS = {
    "director",
    "producer",
    "composer",
    "developer",
    "publisher",
    # vi kan lägga till fler här när vi ser dem dyka upp (designer, programmer, artist, etc.)
    "designer",
    "programmer",
    "artist",
}

def looks_like_snes(plat_label: str) -> bool:
    if not plat_label:
        return False
    txt = plat_label.lower()
    return ("super nintendo" in txt) or ("super famicom" in txt)

def find_wikidata_candidates(game_title: str):
    sparql = f"""
    SELECT ?game ?gameLabel ?platformLabel ?pubdate WHERE {{
      ?game wdt:P31 wd:Q7889 .

      {{
        ?game rdfs:label "{game_title}"@en .
      }}
      UNION
      {{
        ?game wdt:P1476 ?titleStmt .
        FILTER(STR(?titleStmt) = "{game_title}")
      }}

      OPTIONAL {{ ?game wdt:P400 ?platform . }}
      OPTIONAL {{ ?game wdt:P577 ?pubdate . }}

      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "en".
      }}
    }}
    """

    resp = requests.get(
        WIKIDATA_ENDPOINT,
        params={"query": sparql, "format": "json"},
        headers=HEADERS,
        timeout=30
    )
    data = resp.json()
    bindings = data.get("results", {}).get("bindings", [])

    by_qid = {}
    for b in bindings:
        game_uri = b["game"]["value"]
        qid = game_uri.rsplit("/",1)[-1]
        label_here = b.get("gameLabel",{}).get("value","")
        plat_label = b.get("platformLabel",{}).get("value","")
        pubdate_val = b.get("pubdate",{}).get("value","")

        if qid not in by_qid:
            by_qid[qid] = {
                "qid": qid,
                "label": label_here,
                "platforms": [],
                "years": set()
            }

        if plat_label:
            by_qid[qid]["platforms"].append(plat_label)

        if pubdate_val and len(pubdate_val) >= 4:
            year = pubdate_val[0:4]
            if year.isdigit():
                by_qid[qid]["years"].add(year)

    out = []
    for qid, info in by_qid.items():
        plats = info["platforms"]
        years_sorted = sorted(info["years"])
        out.append({
            "qid": qid,
            "label": info["label"],
            "platforms": plats,
            "years": years_sorted,
            "is_snes_like": any(looks_like_snes(p) for p in plats),
        })
    return out

def pick_best_candidate(candidates):
    # välj första kandidat som är SNES-lik
    for cand in candidates:
        if cand["is_snes_like"]:
            return cand
    # fallback: ingen SNES-träff → returnera None (hellre None än felmatch)
    return None

def fetch_credits(qid: str):
    sparql_roles = f"""
    SELECT ?prop ?propLabel ?who ?whoLabel ?whoType WHERE {{
      VALUES ?game {{ wd:{qid} }}

      ?game ?p ?who .
      ?who rdfs:label ?whoLabel .
      FILTER(LANG(?whoLabel) = "en")

      ?prop wikibase:directClaim ?p .
      ?prop rdfs:label ?propLabel .
      FILTER(LANG(?propLabel) = "en")

      OPTIONAL {{ ?who wdt:P31 ?whoType . }}
    }}
    """

    resp2 = requests.get(
        WIKIDATA_ENDPOINT,
        params={"query": sparql_roles, "format": "json"},
        headers=HEADERS,
        timeout=30
    )
    data2 = resp2.json()
    bindings2 = data2.get("results", {}).get("bindings", [])

    credits = []
    for b in bindings2:
        role_label = b.get("propLabel",{}).get("value","").strip()
        who_label  = b.get("whoLabel",{}).get("value","").strip()
        who_type_uri = b.get("whoType",{}).get("value","")

        # bara roller vi bryr oss om
        if role_label.lower() not in CREDIT_PROPS:
            continue

        who_type = "org/other"
        if who_type_uri.endswith("/Q5"):
            who_type = "person"

        credits.append({
            "role": role_label,
            "who": who_label,
            "who_type": who_type
        })

    # dedupe
    uniq = {}
    for c in credits:
        k = (c["role"].lower(), c["who"].lower(), c["who_type"])
        uniq[k] = c
    out = list(uniq.values())

    # sortera stabilt: personer först
    out.sort(key=lambda x: (0 if x["who_type"]=="person" else 1, x["role"].lower(), x["who"].lower()))
    return out

def main():
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    subset = rows[:MAX_ROWS]

    link_rows = []
    credit_rows = []

    for row in subset:
        eid = row["edition_id"]
        title = row["title_primary"]

        print("====================================================")
        print(f"edition_id : {eid}")
        print(f"title      : {title}")
        print()

        cands = find_wikidata_candidates(title)
        if not cands:
            print("  -> no wikidata candidates at all")
            continue

        # visa kandidater kort för QA
        for cand in cands:
            plats_short = ", ".join(sorted(set(cand["platforms"])))
            years_short = ", ".join(cand["years"])
            print(f"  cand {cand['qid']} ({cand['label']})")
            print(f"    platforms: {plats_short}")
            print(f"    years:     {years_short}")
            print(f"    snes_like: {cand['is_snes_like']}")
        print()

        best = pick_best_candidate(cands)
        if not best:
            print("  -> no SNES-like candidate selected, SKIPPING this edition")
            continue

        print(f"[PICKED] {best['qid']} ({best['label']})")
        print(f"         platforms: {', '.join(sorted(set(best['platforms'])))}")
        print(f"         years:     {', '.join(best['years'])}")
        print()

        # spara länkrow som vi *skulle* skriva till wd_links.csv
        link_rows.append({
            "edition_id": eid,
            "title_primary": title,
            "wd_qid": best["qid"],
            "wd_label": best["label"],
        })

        # hämta och skriv ut credits
        creds = fetch_credits(best["qid"])
        if not creds:
            print("  [CREDITS] (none found)")
        else:
            print("  [CREDITS]")
            for c in creds:
                print(f"    {c['role']} -> {c['who']} [{c['who_type']}]")
                credit_rows.append({
                    "edition_id": eid,
                    "wd_qid": best["qid"],
                    "role": c["role"],
                    "who": c["who"],
                    "who_type": c["who_type"],
                })

        print()

    # summering i slutet
    print("====================================================")
    print(f"SUMMARY: would link {len(link_rows)} editions and {len(credit_rows)} credit rows")
    print("First few link rows:")
    for r in link_rows[:5]:
        print("  ", r)
    print("First few credit rows:")
    for r in credit_rows[:10]:
        print("  ", r)

if __name__ == "__main__":
    main()
