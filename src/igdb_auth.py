# igdb_auth.py
import json
import time
from pathlib import Path
import requests
from config import get_twitch_client_id, get_twitch_client_secret

TOKEN_CACHE = Path(".igdb_token.json")
TWITCH_OAUTH_URL = "https://id.twitch.tv/oauth2/token"

def _read_cached_token():
    if TOKEN_CACHE.exists():
        try:
            data = json.load(TOKEN_CACHE.open())
            # spara en liten buffert så vi inte hamnar precis vid utgång
            if data.get("access_token") and data.get("expires_at", 0) > time.time() + 60:
                return data["access_token"]
        except Exception:
            pass
    return None

def _write_cached_token(access_token: str, expires_in: int):
    payload = {
        "access_token": access_token,
        "expires_at": int(time.time()) + int(expires_in)
    }
    TOKEN_CACHE.write_text(json.dumps(payload, indent=2))

def get_access_token() -> str:
    cached = _read_cached_token()
    if cached:
        return cached

    resp = requests.post(
        TWITCH_OAUTH_URL,
        params={
            "client_id": get_twitch_client_id(),
            "client_secret": get_twitch_client_secret(),
            "grant_type": "client_credentials",
        },
        timeout=20
    )
    resp.raise_for_status()
    data = resp.json()
    access_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    _write_cached_token(access_token, expires_in)
    return access_token