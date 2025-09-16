# config.py
import os
from dotenv import load_dotenv

# Laddas en gång i processens början
load_dotenv()

def get_twitch_client_id() -> str:
    cid = os.getenv("TWITCH_CLIENT_ID")
    if not cid:
        raise RuntimeError("Saknar TWITCH_CLIENT_ID i .env")
    return cid

def get_twitch_client_secret() -> str:
    secret = os.getenv("TWITCH_CLIENT_SECRET")
    if not secret:
        raise RuntimeError("Saknar TWITCH_CLIENT_SECRET i .env")
    return secret