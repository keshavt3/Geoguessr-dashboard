import time
import json
from .utils import calculate_score, parse_time

BASE_FEED_URL = "https://www.geoguessr.com/api/v4/feed/private"
BASE_DUEL_URL = "https://game-server.geoguessr.com/api/duels/"

def fetch_filtered_tokens(session, game_type="team", mode_filter="all"):
    results = []
    token = None
    page = 1

    while True:
        print(f"Fetching feed page {page}...")
        url = BASE_FEED_URL
        if token:
            url += f"?paginationToken={token}"

        resp = session.get(url)  # Use session.get instead of requests.get

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

                    results.append(game_id)

        token = data.get("paginationToken")
        if not token:
            break
        page += 1
        time.sleep(0.3)  # avoid hammering server

    return list(set(results))  # unique

def fetch_team_duels(session, game_ids, my_id, teammate_id=None):
    all_results = []

    total_games = len(game_ids)
    for i, game_id in enumerate(game_ids, 1):
        print(f"Processing game {i}/{total_games} (ID: {game_id})...")
        try:
            resp = session.get(BASE_DUEL_URL + game_id)  # Use session.get
            if resp.status_code != 200:
                print(f"Failed to fetch game {game_id}: {resp.status_code}")
                continue

            game = resp.json()

            # Find my team and enemy team
            my_team = next((t for t in game["teams"] if any(p["playerId"] == my_id for p in t["players"])), None)
            if not my_team:
                continue
            enemy_team = next((t for t in game["teams"] if t["id"] != my_team["id"]), None)

            if teammate_id and not any(p["playerId"] == teammate_id for p in my_team["players"]):
                continue

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

                    p_stats["rounds"].append({
                        "roundNumber": guess["roundNumber"],
                        "distance": guess["distance"],
                        "score": guess["score"],
                        "time": round_time,
                        "country": round_info.get("panorama", {}).get("countryCode"),
                        "lat": guess["lat"],
                        "lng": guess["lng"]
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

            all_results.append({
                "gameId": game_id,
                "teamId": my_team["id"],
                "teamStats": team_stats,
                "playerStats": player_stats,
                "roundStats": round_stats
            })
            time.sleep(0.1)
        except Exception as e:
            print("Error fetching game", game_id, e)

    return all_results
