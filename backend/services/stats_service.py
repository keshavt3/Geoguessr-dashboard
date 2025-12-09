import requests
from geoguessr.process_stats import process_duels
from geoguessr.fetch_games import fetch_filtered_tokens, fetch_duels
from geoguessr.utils import load_data, save_json

DATA_PATH = 'data/games.json'
PROCESSED_PATH = 'data/processed_stats.json'

def get_stats():
    stats = load_data(PROCESSED_PATH)
    return stats

def fetch_and_process(player_id, ncfa_cookie):
    if not ncfa_cookie:
        raise ValueError("ncfa_cookie is required")

    session = requests.Session()
    session.cookies.set("_ncfa", ncfa_cookie, domain="www.geoguessr.com")
    session.cookies.set("_ncfa", ncfa_cookie, domain="game-server.geoguessr.com")

    game_ids = fetch_filtered_tokens(session, game_type="duels")
    games = fetch_duels(session, game_ids, player_id)

    save_json(DATA_PATH, games)

    stats = process_duels(games)
    save_json(PROCESSED_PATH, stats)
