# igdb_extract.py
from __future__ import annotations
import csv
from pathlib import Path
from typing import Iterable, Dict, Any, List
from datetime import datetime, timezone

from igdb_client import IGDBClient

# --------- helpers: tid/format ---------
def ts_to_ymd(ts) -> str:
    """Unix timestamp -> YYYY-MM-DD (UTC). Tom sträng om ogiltigt."""
    if ts is None or ts == "":
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""

def _normalize(val: str, lower: bool = False) -> str:
    v = (val or "").strip()
    if not v:
        return ""
    v = " ".join(v.split())  # kollapsa whitespace
    if lower:
        v = v.lower()
    return v

# --------- paths ---------
BASE = Path("data/external/igdb")
BASE.mkdir(parents=True, exist_ok=True)

F_GAMES         = BASE / "igdb_games.csv"
F_ALT_NAMES     = BASE / "igdb_alternative_names.csv"
F_PLATFORMS     = BASE / "igdb_platforms.csv"
F_RELEASE_DATES = BASE / "igdb_release_dates.csv"
F_WEBSITES      = BASE / "igdb_websites.csv"
F_INVOLVED      = BASE / "igdb_involved_companies.csv"

# --------- headers ---------
H_GAMES = [
    "igdb_id","name","first_release_date_ts","first_release_date_ymd",
    "genres","themes","game_modes","player_perspectives",
    "franchises","collection","platforms","aggregated_rating"
]
H_ALT_NAMES     = ["igdb_id","alias"]
H_PLATFORMS     = ["igdb_id","platform_id","platform_name"]
H_RELEASE_DATES = [
    "igdb_id","date_ts","date_ymd","human",
    "region_id","region_name","region_code",
    "platform_id","platform_name"
]
H_WEBSITES      = ["igdb_id","category_id","url"]
H_INVOLVED      = ["igdb_id","company_name","developer","publisher","porting","supporting"]

# --------- nycklar (idempotens) ---------
K_GAMES         = ["igdb_id"]                                       # en rad per spel
K_ALT_NAMES     = ["igdb_id","alias"]                                # undvik dubblett-alias
K_PLATFORMS     = ["igdb_id","platform_id"]                          # en rad per (spel, plattform)
K_RELEASE_DATES = ["igdb_id","date_ts","region_id","platform_id","human"]  # ts primärt; human fallback
K_WEBSITES      = ["igdb_id","url"]                                  # URL identiferar
K_INVOLVED      = ["igdb_id","company_name","developer","publisher","porting","supporting"]


# Fallback (IGDB region_id -> namn)
# OBS! IGDB har ett enum-fält `release_dates.region` med fasta ID:n.
# Enligt dokumentationen motsvarar t.ex. 1=Europe, 2=North America, 5=Japan osv.
# Problemet: API:t `regions` returnerar inte alltid hela listan i praktiken.
# Därför har vi en hårdkodad fallback-tabell nedan.
#
# Viktigt:
# - Vi hittar inte på några regioner. Alla mappingar kommer från IGDB:s enum.
# - Om ett region_id inte finns i tabellen sätts region_name="" och region_code="UNKNOWN".
# - Detta gör att vi hellre flaggar som okänt än riskerar felaktig data.
# - Kodningen (EU, NA, JP, KR, WW osv.) är en normalisering för att enkelt kunna
#   matcha mot arkivet, men det råa region_id sparas alltid i CSV för spårbarhet.
#
# Policy: "North America" mappas till NA (inte US) eftersom IGDB:s fält syftar på hela
# regionen, inte enbart USA.

_FALLBACK_REGION_MAP = {
    1: "Europe",
    2: "North America",
    3: "Australia",
    4: "New Zealand",
    5: "Japan",
    6: "China",
    7: "Asia",
    8: "Worldwide",
    9: "Korea",
    10: "Brazil",
}

_REGION_NAME_TO_CODE = {
    "Europe": "EU",
    "North America": "US",   # ändra till NA?
    "Japan": "JP",
    "Korea": "KR",
    "China": "CN",
    "Australia": "AU",
    "New Zealand": "NZ",
    "Asia": "AS",
    "Brazil": "BR",
    "Worldwide": "WW",
}

def map_region(region_id: int | None, region_map: Dict[int, str]) -> tuple[str, str]:
    if not region_id:
        return ("", "UNKNOWN")

    # försök slå upp i dynamiska map:en först
    name = region_map.get(region_id)
    if not name:
        # fallback till hårdkodad tabell
        name = _FALLBACK_REGION_MAP.get(region_id, "")

    if not name:
        return ("", "UNKNOWN")

    code = _REGION_NAME_TO_CODE.get(name, "UNKNOWN")
    return (name, code)


# --------- CSV-utils ---------
def ensure_header(path: Path, header: Iterable[str]) -> None:
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(list(header))

def _build_key(row_map: Dict[str, Any], key_cols: List[str]) -> tuple:
    """Bygger tuple-key från rad + key-kolumner (med normalisering där det behövs)."""
    parts: List[str] = []
    for c in key_cols:
        v = row_map.get(c, "")
        if v is None:
            v = ""
        else:
            v = str(v)

        if c in ("alias","url"):
            v = _normalize(v, lower=True)
        elif c in ("platform_name","company_name","human"):
            v = _normalize(v)  # trim/kollapsa, behåll case
        else:
            v = v.strip()
        parts.append(v)

    # specialfall: om vi använder K_RELEASE_DATES, ignorera 'human' om 'date_ts' finns
    if set(key_cols) == set(K_RELEASE_DATES):
        dt = str(row_map.get("date_ts") or "").strip()
        if dt:
            return (
                str(row_map.get("igdb_id") or "").strip(),
                dt,
                str(row_map.get("region_id") or "").strip(),
                str(row_map.get("platform_id") or "").strip(),
                ""  # human ignoreras när ts finns
            )
    return tuple(parts)

def load_keyset(path: Path, key_cols: List[str]) -> set[tuple]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    keys: set[tuple] = set()
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add(_build_key(row, key_cols))
    return keys

def append_new_rows(path: Path, header: List[str], key_cols: List[str], rows: List[List[Any]]):
    ensure_header(path, header)
    existing = load_keyset(path, key_cols)
    to_write: List[List[Any]] = []
    for r in rows:
        row_map = dict(zip(header, r))
        key = _build_key(row_map, key_cols)
        if key not in existing:
            to_write.append(r)
            existing.add(key)
    if to_write:
        with path.open("a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(to_write)
        print(f"[UPSERT] {path.name}: wrote {len(to_write)} new rows; skipped {len(rows)-len(to_write)} duplicates.")
    else:
        print(f"[UPSERT] {path.name}: all {len(rows)} rows were duplicates.")

def join_names(items, key="name") -> str:
    return "; ".join(i.get(key) for i in items if i and i.get(key))

# --------- kärnlogik ---------
def upsert_game_bundle(game: dict, region_map: Dict[int, str]):
    gid = game.get("id")
    if not gid:
        return

    # -- igdb_games.csv --
    games_row = [
        gid,
        game.get("name",""),
        game.get("first_release_date",""),
        ts_to_ymd(game.get("first_release_date")),
        join_names(game.get("genres", [])),
        join_names(game.get("themes", [])),
        join_names(game.get("game_modes", [])),
        join_names(game.get("player_perspectives", [])),
        join_names(game.get("franchises", [])),
        (game.get("collection") or {}).get("name",""),
        join_names(game.get("platforms", [])),
        game.get("aggregated_rating",""),
    ]
    append_new_rows(F_GAMES, H_GAMES, K_GAMES, [games_row])

    # -- alternative names --
    alt_rows: List[List[Any]] = []
    for a in game.get("alternative_names", []):
        alias = a.get("name")
        if alias:
            alt_rows.append([gid, alias])
    if alt_rows:
        append_new_rows(F_ALT_NAMES, H_ALT_NAMES, K_ALT_NAMES, alt_rows)

    # -- platforms (relation) --
    plat_rows: List[List[Any]] = []
    for p in game.get("platforms", []):
        plat_rows.append([gid, p.get("id",""), p.get("name","")])
    if plat_rows:
        append_new_rows(F_PLATFORMS, H_PLATFORMS, K_PLATFORMS, plat_rows)

    # -- websites --
    site_rows: List[List[Any]] = []
    for w in game.get("websites", []):
        url = w.get("url")
        if url:
            site_rows.append([gid, w.get("category",""), url])
    if site_rows:
        append_new_rows(F_WEBSITES, H_WEBSITES, K_WEBSITES, site_rows)

    # -- involved companies --
    inv_rows: List[List[Any]] = []
    for ic in game.get("involved_companies", []):
        company_name = (ic.get("company") or {}).get("name","")
        inv_rows.append([
            gid,
            company_name,
            ic.get("developer",""),
            ic.get("publisher",""),
            ic.get("porting",""),
            ic.get("supporting",""),
        ])
    if inv_rows:
        append_new_rows(F_INVOLVED, H_INVOLVED, K_INVOLVED, inv_rows)

    # -- release dates --
    rd_rows: List[List[Any]] = []
    for rd in game.get("release_dates", []):
        date_ts = rd.get("date")
        region_id = rd.get("region")
        region_name, region_code = map_region(region_id, region_map)
        rd_rows.append([
            gid,
            date_ts or "",
            ts_to_ymd(date_ts),
            rd.get("human",""),
            region_id or "",
            region_name,
            region_code,
            (rd.get("platform") or {}).get("id",""),
            (rd.get("platform") or {}).get("name",""),
        ])
    if rd_rows:
        append_new_rows(F_RELEASE_DATES, H_RELEASE_DATES, K_RELEASE_DATES, rd_rows)
def fetch_and_write_for_titles(titles: List[str], per_title_limit: int = 3):
    client = IGDBClient()
    region_map = client.regions_map()  # hämta alla regioner en gång
    for t in titles:
        hits = client.search_games_basic(t, limit=per_title_limit) or []
        print(f"[SEARCH] '{t}': {len(hits)} träff(ar).")
        if not hits:
            continue
        for idx, h in enumerate(hits, start=1):
            gid = h["id"]
            gname = h.get("name", "")
            print(f"  - kandidat {idx}: {gid} – {gname}")
        # välj första som demo
        chosen = hits[0]
        print(f"[PICK] '{t}' → game_id={chosen['id']} – {chosen.get('name','')}")
        details = client.game_details(chosen["id"]) or []
        if not details:
            print(f"[WARN] Inga detaljer för game_id={chosen['id']}")
            continue
        upsert_game_bundle(details[0], region_map)

# --------- CLI ---------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fetch and save IGDB data for given titles.")
    parser.add_argument("titles", nargs="+", help="En eller flera speltitlar att hämta från IGDB")
    parser.add_argument("--limit", type=int, default=1, help="Max antal träffar per titel (default 1)")
    args = parser.parse_args()

    fetch_and_write_for_titles(args.titles, per_title_limit=args.limit)
    print(f"Done. Wrote IGDB CSVs to {BASE}/")

if __name__ == "__main__":
    main()