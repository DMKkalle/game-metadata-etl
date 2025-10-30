# igdb_client.py
import time
import requests
from igdb_auth import get_access_token
from config import get_twitch_client_id

IGDB_BASE = "https://api.igdb.com/v4"

class IGDBClient:
    def __init__(self, sleep_between=0.30):
        self.client_id = get_twitch_client_id()
        self.sleep_between = sleep_between
        self._token = None

    @property
    def token(self):
        if not self._token:
            self._token = get_access_token()
        return self._token

    def _headers(self):
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}",
        }

    def post(self, endpoint: str, query: str):
        url = f"{IGDB_BASE}/{endpoint}"
        time.sleep(self.sleep_between)
        resp = requests.post(url, data=query, headers=self._headers(), timeout=30)

        if resp.status_code == 401:
            self._token = None
            time.sleep(0.2)
            resp = requests.post(url, data=query, headers=self._headers(), timeout=30)

        if resp.status_code == 429:
            time.sleep(0.7)
            resp = requests.post(url, data=query, headers=self._headers(), timeout=30)

        resp.raise_for_status()
        return resp.json()

    def search_games_basic(self, title: str, limit: int = 10, offset: int = 0):
        q = f"""
        fields id,name,first_release_date,platforms.name,genres.name,aggregated_rating,summary;
        search "{title}";
        where version_parent = null;
        limit {limit};
        offset {offset};
        """
        return self.post("games", q)

    def game_companies(self, game_id: int):
        q = f"""
        fields id,company.name,developer,publisher,porting,supporting;
        where game = {game_id};
        """
        return self.post("involved_companies", q)

    def game_release_dates(self, game_id: int):
        q = f"""
        fields id,date,human,region,platform,name,category,updated_at;
        where game = {game_id};
        """
        return self.post("release_dates", q)
    
    def game_details(self, game_id: int):
        q = f"""
        fields
            id,
            name,
            first_release_date,
            genres.name,
            themes.name,
            game_modes.name,
            player_perspectives.name,
            franchises.name,
            collection.name,
            alternative_names.name,
            websites.url,
            involved_companies.company.name,
            involved_companies.developer,
            involved_companies.publisher,
            involved_companies.porting,
            involved_companies.supporting,
            release_dates.date,
            release_dates.human,
            release_dates.region,
            release_dates.platform.name,
            platforms.name,
            aggregated_rating,
            cover.image_id;
        where id = {game_id};
        """
        return self.post("games", q)


    def regions_map(self):
        """Fetch a {region_id: region_name} mapping from IGDB."""
        q = "fields id,name; limit 50;"
        rows = self.post("regions", q)
        return {row["id"]: row["name"] for row in rows if "id" in row and "name" in row}