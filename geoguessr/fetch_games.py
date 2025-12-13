import time
import json
import requests
from .utils import calculate_score, parse_time, save_json

BASE_FEED_URL = "https://www.geoguessr.com/api/v4/feed/private"
BASE_DUEL_URL = "https://game-server.geoguessr.com/api/duels/"

def fetch_filtered_tokens(session, game_type="team", mode_filter="all"):
    """Fetch game IDs from feed.

    Returns:
        dict: {game_id: is_competitive} mapping
    """
    results = {}  # game_id -> is_competitive
    token = None
    page = 1

    while True:
        print(f"Fetching feed page {page}...")
        url = BASE_FEED_URL
        if token:
            url += f"?paginationToken={token}"

        resp = session.get(url)

        if resp.status_code != 200:
            print("Auth failed or other error:", resp.status_code)
            break

        data = resp.json()
        if not data.get("entries"):
            break

        for entry in data["entries"]:
            payload_raw = entry.get("payload")
            if isinstance(payload_raw, str):
                try:
                    parsed = json.loads(payload_raw)
                except json.JSONDecodeError:
                    continue
                items = parsed if isinstance(parsed, list) else [parsed]

                for item in items:
                    payload = item.get("payload", {})
                    game_mode = item.get("gameMode") or payload.get("gameMode")
                    game_id = item.get("gameId") or payload.get("gameId")
                    competitive_mode = payload.get("competitiveGameMode")
                    is_competitive = competitive_mode and competitive_mode != "None"

                    if not game_id or not game_mode:
                        continue
                    if game_type == "team" and game_mode != "TeamDuels":
                        continue
                    if game_type == "duels" and game_mode == "TeamDuels":
                        continue
                    if mode_filter == "competitive" and not is_competitive:
                        continue
                    if mode_filter == "casual" and is_competitive:
                        continue

                    results[game_id] = is_competitive

        token = data.get("paginationToken")
        if not token:
            break
        page += 1
        time.sleep(0.075)

    return results

def fetch_single_team_duel(session, game_id, my_id, is_competitive=False, teammate_id=None):
    """Fetch and process a single team duel game.

    Returns:
        dict: Processed game data, or None if game should be skipped
    """
    try:
        resp = session.get(BASE_DUEL_URL + game_id)
        if resp.status_code != 200:
            print(f"Failed to fetch game {game_id}: {resp.status_code}")
            return None

        game = resp.json()

        # Validate this is a standard 2v2 team duel (exactly 2 teams, 2 players each)
        teams = game.get("teams", [])
        if len(teams) != 2:
            print(f"Skipping game {game_id}: expected 2 teams, got {len(teams)}")
            return None
        if any(len(t.get("players", [])) != 2 for t in teams):
            player_counts = [len(t.get("players", [])) for t in teams]
            print(f"Skipping game {game_id}: expected 2 players per team, got {player_counts}")
            return None

        # Find my team and enemy team
        my_team = next((t for t in game["teams"] if any(p["playerId"] == my_id for p in t["players"])), None)
        if not my_team:
            return None
        enemy_team = next((t for t in game["teams"] if t["id"] != my_team["id"]), None)

        if teammate_id and not any(p["playerId"] == teammate_id for p in my_team["players"]):
            return None

        team_stats = {"totalDistance": 0, "totalScore": 0, "totalRounds": 0, "totalHealthChange": 0}
        player_stats = {}
        rounds_map = {}
        enemy_best = {}

        # Compute enemy best per round
        for player in enemy_team["players"]:
            for guess in player["guesses"]:
                rn = guess["roundNumber"]
                score = guess.get("score") or calculate_score(guess["distance"])
                enemy_best[rn] = max(score, enemy_best.get(rn, 0))

        # Process player guesses
        for player in my_team["players"]:
            p_stats = {"distance": 0, "score": 0, "rounds": []}
            for guess in player["guesses"]:
                if guess.get("score") is None:
                    guess["score"] = calculate_score(guess["distance"])
                round_info = game["rounds"][guess["roundNumber"] - 1]
                round_time = (parse_time(guess["created"]) - parse_time(round_info["startTime"])).total_seconds()

                p_stats["distance"] += guess["distance"]
                p_stats["score"] += guess["score"]

                panorama = round_info.get("panorama", {})
                p_stats["rounds"].append({
                    "roundNumber": guess["roundNumber"],
                    "distance": guess["distance"],
                    "score": guess["score"],
                    "time": round_time,
                    "country": panorama.get("countryCode"),
                    "lat": guess["lat"],
                    "lng": guess["lng"],
                    "actualLat": panorama.get("lat"),
                    "actualLng": panorama.get("lng")
                })

                r = rounds_map.setdefault(guess["roundNumber"], {"totalDistance": 0, "totalScore": 0, "totalHealthChange": 0, "countries": set()})
                r["totalDistance"] += guess["distance"]
                r["totalScore"] += guess["score"]
                country = round_info.get("panorama", {}).get("countryCode")
                if country:
                    r["countries"].add(country)

            team_stats["totalDistance"] += p_stats["distance"]
            team_stats["totalScore"] += p_stats["score"]
            team_stats["totalRounds"] += len(player["guesses"])
            player_stats[player["playerId"]] = p_stats

        # Health changes
        for rr in my_team.get("roundResults", []):
            if rr.get("healthBefore") is not None and rr.get("healthAfter") is not None:
                delta = rr["healthAfter"] - rr["healthBefore"]
                team_stats["totalHealthChange"] += delta
                r = rounds_map.setdefault(rr["roundNumber"], {"totalDistance": 0, "totalScore": 0, "totalHealthChange": 0, "countries": set()})
                r["totalHealthChange"] = delta

        # Score diff
        enemy_total_score = sum(
            guess.get("score") or calculate_score(guess["distance"])
            for p in enemy_team["players"]
            for guess in p["guesses"]
        )
        team_stats["scoreDiff"] = team_stats["totalScore"] - enemy_total_score

        round_stats = [
            {
                "roundNumber": rn,
                "totalDistance": r["totalDistance"],
                "totalScore": r["totalScore"],
                "totalHealthChange": r["totalHealthChange"],
                "countries": list(r["countries"]),
                "enemyBestScore": enemy_best.get(rn, 0)
            } for rn, r in rounds_map.items()
        ]

        return {
            "gameId": game_id,
            "isCompetitive": is_competitive,
            "teamId": my_team["id"],
            "teamStats": team_stats,
            "playerStats": player_stats,
            "roundStats": round_stats
        }
    except Exception as e:
        print("Error fetching game", game_id, e)
        return None


def fetch_team_duels(session, game_ids_with_mode, my_id, teammate_id=None):
    """Fetch team duels game details.

    Args:
        game_ids_with_mode: dict {game_id: is_competitive} or list of game_ids
    """
    # Handle both dict and list for backwards compatibility
    if isinstance(game_ids_with_mode, dict):
        game_ids = list(game_ids_with_mode.keys())
        mode_map = game_ids_with_mode
    else:
        game_ids = game_ids_with_mode
        mode_map = {}

    all_results = []

    total_games = len(game_ids)
    for i, game_id in enumerate(game_ids, 1):
        print(f"Processing game {i}/{total_games} (ID: {game_id})...")
        is_competitive = mode_map.get(game_id, False)
        result = fetch_single_team_duel(session, game_id, my_id, is_competitive, teammate_id)
        if result:
            all_results.append(result)
        time.sleep(0.075)

    return all_results

def fetch_single_duel(session, game_id, my_id, is_competitive=False):
    """Fetch and process a single solo duel game.

    Returns:
        dict: Processed game data, or None if game should be skipped
    """
    try:
        resp = session.get(BASE_DUEL_URL + game_id)
        if resp.status_code != 200:
            print(f"Failed to fetch game {game_id}: {resp.status_code}")
            return None

        game = resp.json()

        # Validate this is a standard 1v1 duel (exactly 2 teams, 1 player each)
        teams = game.get("teams", [])
        if len(teams) != 2:
            print(f"Skipping game {game_id}: expected 2 teams, got {len(teams)}")
            return None
        if any(len(t.get("players", [])) != 1 for t in teams):
            player_counts = [len(t.get("players", [])) for t in teams]
            print(f"Skipping game {game_id}: expected 1 player per team, got {player_counts}")
            return None

        # Identify me and the enemy
        my_player = None
        my_team = None
        enemy_player = None
        for team in game["teams"]:
            for player in team["players"]:
                if player["playerId"] == my_id:
                    my_player = player
                    my_team = team
                else:
                    enemy_player = player

        if not my_player or not enemy_player:
            print(f"Skipping game {game_id}: player not found in game")
            return None

        # Prepare per-round stats
        rounds_map = {}

        # Enemy best score per round
        enemy_best = {}
        for guess in enemy_player["guesses"]:
            rn = guess["roundNumber"]
            score = guess.get("score") or calculate_score(guess["distance"])
            enemy_best[rn] = max(score, enemy_best.get(rn, 0))

        # My guesses
        my_stats = {"totalDistance": 0, "totalScore": 0, "rounds": []}
        for guess in my_player["guesses"]:
            if guess.get("score") is None:
                guess["score"] = calculate_score(guess["distance"])
            round_info = game["rounds"][guess["roundNumber"] - 1]
            round_time = (parse_time(guess["created"]) - parse_time(round_info["startTime"])).total_seconds()

            my_stats["totalDistance"] += guess["distance"]
            my_stats["totalScore"] += guess["score"]

            r = rounds_map.setdefault(guess["roundNumber"], {"myScore": 0, "enemyScore": 0, "totalHealthChange": 0, "country": None})
            panorama = round_info.get("panorama", {})
            r["myScore"] = guess["score"]
            r["country"] = panorama.get("countryCode")

            my_stats["rounds"].append({
                "roundNumber": guess["roundNumber"],
                "distance": guess["distance"],
                "score": guess["score"],
                "time": round_time,
                "country": r["country"],
                "lat": guess["lat"],
                "lng": guess["lng"],
                "actualLat": panorama.get("lat"),
                "actualLng": panorama.get("lng")
            })

        # Health changes and enemy scores
        for rr in my_team.get("roundResults", []):
            rn = rr["roundNumber"]
            r = rounds_map.setdefault(rn, {"myScore": 0, "enemyScore": 0, "totalHealthChange": 0, "country": None})
            if rr.get("healthBefore") is not None and rr.get("healthAfter") is not None:
                r["totalHealthChange"] = rr["healthAfter"] - rr["healthBefore"]
            # Enemy score per round
            r["enemyScore"] = enemy_best.get(rn, 0)

        round_stats = [
            {
                "roundNumber": rn,
                "myScore": r["myScore"],
                "enemyScore": r["enemyScore"],
                "totalHealthChange": r["totalHealthChange"],
                "country": r["country"]
            }
            for rn, r in rounds_map.items()
        ]

        return {
            "gameId": game_id,
            "isCompetitive": is_competitive,
            "playerStats": my_stats,
            "roundStats": round_stats
        }
    except Exception as e:
        print("Error fetching game", game_id, e)
        return None


def fetch_duels(session, game_ids_with_mode, my_id):
    """Fetch solo duels game details.

    Args:
        game_ids_with_mode: dict {game_id: is_competitive} or list of game_ids
    """
    # Handle both dict and list for backwards compatibility
    if isinstance(game_ids_with_mode, dict):
        game_ids = list(game_ids_with_mode.keys())
        mode_map = game_ids_with_mode
    else:
        game_ids = game_ids_with_mode
        mode_map = {}
    all_results = []

    total_games = len(game_ids)
    for i, game_id in enumerate(game_ids, 1):
        print(f"Processing game {i}/{total_games} (ID: {game_id})...")
        is_competitive = mode_map.get(game_id, False)
        result = fetch_single_duel(session, game_id, my_id, is_competitive)
        if result:
            all_results.append(result)
        time.sleep(0.075)

    return all_results





if __name__ == "__main__":
    ncfa = input("Enter your ncfa cookie: ")
    player_id = input("Enter your player ID: ")
    teammate_id = input("Enter teammate ID (optional, press Enter to skip): ") or None
    game_type = input("Game type ('team' or 'duels', default 'team'): ") or "team"
    mode_filter = input("Mode filter ('all', 'competitive', 'casual', default 'all'): ") or "all"

    # Create a session
    session = requests.Session()
    session.cookies.set("_ncfa", ncfa, domain="www.geoguessr.com")
    session.cookies.set("_ncfa", ncfa, domain="game-server.geoguessr.com")


    # Then call the functions with session
    game_tokens = ["3321914e-48ec-45c4-8689-c2dcc2bdeb9b","ba6de9ed-f51b-46bd-a2f6-c1b6ad935234", "ea7ff46d-7048-45b6-9817-cfc74d1a0252"]
    if game_type == "team":
        games = fetch_team_duels(session, game_tokens, player_id, teammate_id)
    elif game_type == "duels":
        games = fetch_duels(session, game_tokens, player_id)
    else:
        print("Invalid game type. Choose 'team' or 'duels'.")


    save_json("data/games.json", games)

    print(f"Saved {len(games)} games.")