#!/usr/bin/env python3
import os, time, requests
from urllib.parse import urlencode
from dotenv import load_dotenv

BASE = "https://www.giantbomb.com/api"

def _gb_get(path: str, params: dict, sleep: float = 1.0) -> dict:
    load_dotenv()
    key = os.getenv("GIANTBOMB_API_KEY")
    if not key:
        raise RuntimeError("Saknar GIANTBOMB_API_KEY i .env")
    ua = os.getenv("GB_USER_AGENT", "Exjobb-Embracer-GB/0.1 (contact: you@example.com)")
    q = {"api_key": key, "format": "json", **params}
    url = f"{BASE}{path}?{urlencode(q)}"
    time.sleep(sleep)
    r = requests.get(url, headers={"User-Agent": ua, "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get("error") and data.get("error") != "OK":
        raise RuntimeError(f"GiantBomb error: {data.get('error')}")
    return data

def join_names(items, key="name"):
    if not items:
        return ""
    seen = []
    for it in items:
        nm = (it or {}).get(key) or ""
        nm = nm.strip()
        if nm and nm not in seen:
            seen.append(nm)
    return "; ".join(seen)

def game_detail(game_id: int) -> dict:
    """
    Hämtar detaljer inkl. people (med roller), developers, publishers, releases, bilder.
    """
    fields = ",".join([
        "id","name","platforms","original_release_date","genres",
        "developers","publishers","image","images","site_detail_url",
        # Nyckeln här: 'people' innehåller personobjekt + deras roller
        "people"
    ])
    return _gb_get(f"/game/{int(game_id)}/", {"field_list": fields}).get("results") or {}

def game_releases(game_id: int, limit: int = 50) -> list[dict]:
    return (_gb_get("/releases/", {"filter": f"game:{int(game_id)}", "limit": limit}).get("results")) or []
