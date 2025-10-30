#!/usr/bin/env python3
"""
Snabbtest för Giant Bomb-API:t.
- Läser API-nyckel från .env i projektroten (GIANTBOMB_API_KEY).
- Sökspel: visar träffar (id, namn, plattformar, originalrelease).
- --detail: hämtar detaljer för första träffen (developers, publishers, releases, cover).

Kör:
    python src/gb_test.py "ActRaiser" --limit 5 --detail
"""

import os
import sys
import time
import argparse
from urllib.parse import urlencode
from gb_client import game_releases

import requests
from dotenv import load_dotenv

BASE = "https://www.giantbomb.com/api"

def gb_get(path: str, params: dict, sleep: float = 1.0) -> dict:
    """Gör ett GET-anrop mot Giant Bomb med nyckel/header från .env."""
    key = os.getenv("GIANTBOMB_API_KEY")
    if not key:
        raise RuntimeError("Saknar GIANTBOMB_API_KEY i .env (rotmappen).")
    ua = os.getenv("GB_USER_AGENT", "Exjobb-Embracer-GB/0.1 (contact: you@example.com)")
    q = {"api_key": key, "format": "json", **params}
    url = f"{BASE}{path}?{urlencode(q)}"
    time.sleep(sleep)  # var snäll mot rate-limit
    r = requests.get(url, headers={"User-Agent": ua, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("error") and data.get("error") != "OK":
        raise RuntimeError(f"GiantBomb error: {data.get('error')}")
    return data

def search_games(query: str, limit: int = 5, page: int = 1) -> list[dict]:
    params = {
        "query": query,
        "resources": "game",
        "limit": limit,
        "page": page,
        "field_list": "id,name,platforms,original_release_date"
    }
    return (gb_get("/search/", params).get("results")) or []

def game_detail(game_id: int) -> dict:
    params = {
        "field_list": ",".join([
            "id","name","platforms","original_release_date","genres",
            "developers","publishers","people","releases",
            "image","images","site_detail_url"
        ])
    }
    return gb_get(f"/game/{game_id}/", params).get("results") or {}

def join_names(items, key="name") -> str:
    if not items:
        return ""
    seen = []
    for it in items:
        nm = (it or {}).get(key) or ""
        nm = nm.strip()
        if nm and nm not in seen:
            seen.append(nm)
    return "; ".join(seen)

def main():
    load_dotenv()  # läs .env i projektroten

    ap = argparse.ArgumentParser(description="Sök och testa Giant Bomb API")
    ap.add_argument("query", help="Söksträng (speltitel)")
    ap.add_argument("--limit", type=int, default=5, help="Antal träffar att visa (default 5)")
    ap.add_argument("--detail", action="store_true", help="Visa detaljer för första träffen")
    args = ap.parse_args()

    print(f"[SEARCH] '{args.query}' (limit={args.limit}) …")
    hits = search_games(args.query, limit=args.limit) or []
    if not hits:
        print("Inga träffar.")
        sys.exit(0)

    for i, h in enumerate(hits, start=1):
        plats = join_names(h.get("platforms"))
        print(f"{i}. [{h.get('id')}] {h.get('name')} | Platforms: {plats or '-'} | Original release: {h.get('original_release_date') or '-'}")

    if args.detail:
        first = hits[0]
        gid = first.get("id")
        print("\n[DETAIL] Hämtar detaljer för första träffen …")
        g = game_detail(gid)
        plats_all = join_names(g.get("platforms"))
        genres = join_names(g.get("genres"))
        devs = join_names(g.get("developers"))
        pubs = join_names(g.get("publishers"))
        cover = (g.get("image") or {}).get("super_url") or (g.get("image") or {}).get("medium_url") or ""

        print(f"ID: {g.get('id')}  Name: {g.get('name')}")
        print(f"Platforms: {plats_all or '-'}")
        print(f"Genres: {genres or '-'}")
        print(f"Developers: {devs or '-'}")
        print(f"Publishers: {pubs or '-'}")
        print(f"Original release: {g.get('original_release_date') or '-'}")
        print(f"Cover: {cover or '-'}")
        print(f"Site: {g.get('site_detail_url') or '-'}")

        # Visa ett par releases (om finns)
        rels = game_releases(gid, limit=50)
        if rels:
            print("\nReleases (max 10):")
            for rr in rels[:10]:
                plat = ((rr.get("platform") or {}).get("name")) or "-"
                reg  = ((rr.get("region")   or {}).get("name")) or ""
                dt   = (rr.get("release_date") or rr.get("date_added") or "-")
                print(f"  - {dt} <{plat}{(' | '+reg) if reg else ''}>")
        else:
            print("\nReleases: (inga hittades via /releases/)")

if __name__ == "__main__":
    main()
