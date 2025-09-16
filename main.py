# main.py
from datetime import datetime
from igdb_client import IGDBClient

def ts_to_date(ts):
    if not ts:
        return ""
    try:
        return datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        return str(ts)

def main():
    client = IGDBClient()

    # 1) Snabbsök
    results = client.search_games_basic("Golden Axe", limit=5)
    if not results:
        print("Inga träffar.")
        return

    game_id = results[0]["id"]

    # 2) Hämta region-namn (en gång)
    region_names = client.regions_map()

    # 3) Hämta detaljer
    details_list = client.game_details(game_id)
    if not details_list:
        print("Inga detaljer.")
        return

    g = details_list[0]
    print(f"[{g.get('id')}] {g.get('name')}")
    print("Första release:", ts_to_date(g.get("first_release_date")))
    print("Plattformar:", ", ".join(p["name"] for p in g.get("platforms", []) if "name" in p))
    print("Genrer:", ", ".join(ge["name"] for ge in g.get("genres", []) if "name" in ge))
    print("Webbplatser:", ", ".join(w["url"] for w in g.get("websites", []) if "url" in w))
    print("Alternative names:", ", ".join(a["name"] for a in g.get("alternative_names", []) if "name" in a))

    # Release-datum med human/ts + regionnamn
    for rd in g.get("release_dates", []):
        human = rd.get("human") or ts_to_date(rd.get("date"))
        region_id = rd.get("region")
        region_label = region_names.get(region_id, f"RegionID:{region_id}")
        platform_name = (rd.get("platform") or {}).get("name")
        print(f"Release: {human} | Region: {region_label} | Plattform: {platform_name}")

if __name__ == "__main__":
    main()