from collections import defaultdict
from .utils import load_data, save_json
import reverse_geocoder as rg

def get_country(lat, lon):
    result = rg.search((lat, lon))[0]
    return result['cc']  # country code

def process_games(games, mapsize=14916.862 * 1000):  # mapsize in meters, default is world map diagonal
    # Overall stats
    total_games = 0
    total_wins = 0
    total_rounds = 0
    merchant_stats = {
    "multi_merchant": 0,
    "reverse_merchant": 0
    }
    all_guess_coords = []
    guess_map = {}  # maps (lat, lng) tuple → list of (country_stats_entry, round info)



    # Contribution counts
    player_contrib = defaultdict(int)
    player_rounds = defaultdict(int)

    # Per-player totals
    player_scores = defaultdict(int)
    player_distances = defaultdict(float)
    player_total_5ks = defaultdict(int)

    # NEW: time accumulation
    player_total_time = defaultdict(float)
    player_time_rounds = defaultdict(int)

    # Country stats
    country_stats = defaultdict(lambda: {
        "rounds": 0,
        "team_scores": [],
        "player_scores": defaultdict(list),
        "team_distances": [],
        "player_distances": defaultdict(list),
        "player_5ks": defaultdict(int),
        "score_diffs": [],
        "correct_guesses": 0,   
        "total_guesses": 0,
        "wins": 0, 
    })

    for game in games:
        total_games += 1

        # Win/loss
        if game["teamStats"]["totalHealthChange"] > -6000:
            total_wins += 1

        # Multi-merchant check
        
        score_diff = game["teamStats"].get("scoreDiff", 0)
        lost_game = game["teamStats"]["totalHealthChange"] == -6000
        won_game = game["teamStats"]["totalHealthChange"] > -6000

        # Lost but outplayed opponent
        if lost_game and score_diff > 0:
            merchant_stats["multi_merchant"] += 1

        # Won but got outplayed (inverse)
        if won_game and score_diff < 0:
            merchant_stats["reverse_merchant"] += 1

        # Player IDs (assuming 2 players)
        players = list(game["playerStats"].keys())
        p1, p2 = players[0], players[1]

        rounds_p1 = game["playerStats"][p1]["rounds"]
        rounds_p2 = game["playerStats"][p2]["rounds"]

        rounds_dict_p1 = {r["roundNumber"]: r for r in rounds_p1}
        rounds_dict_p2 = {r["roundNumber"]: r for r in rounds_p2}

        num_rounds = game["roundStats"][-1]["roundNumber"]
        total_rounds += num_rounds

        for rn in range(1, num_rounds + 1):
            r1 = rounds_dict_p1.get(rn)
            r2 = rounds_dict_p2.get(rn)

            if r1 is None:
                score1, dist1, country, time1 = 0, mapsize, None, None
            else:
                score1, dist1, country, time1 = r1["score"], r1["distance"], r1["country"], r1.get("time")

            if r2 is None:
                score2, dist2, _, time2 = 0, mapsize, None, None
            else:
                score2, dist2, _, time2 = r2["score"], r2["distance"], r2["country"], r2.get("time")

            if country is None and r2 is not None:
                country = r2["country"]

            # Team stats
            team_score = max(score1, score2)
            team_distance = min(dist1, dist2)

            # Player aggregates
            player_scores[p1] += score1
            player_scores[p2] += score2
            player_distances[p1] += dist1
            player_distances[p2] += dist2

            # time tracking
            if time1 is not None:
                player_total_time[p1] += time1
                player_time_rounds[p1] += 1
            if time2 is not None:
                player_total_time[p2] += time2
                player_time_rounds[p2] += 1

            # Contribution
            if dist1 < dist2:
                player_contrib[p1] += 1
            elif dist2 < dist1:
                player_contrib[p2] += 1

            player_rounds[p1] += 1
            player_rounds[p2] += 1

            # Country stats
            if country is not None:
                country = country.lower()
                c = country_stats[country]

                # Reverse geocode guess → guess country
                if score1 > score2:
                    key = (r1["lat"], r1["lng"])
                    all_guess_coords.append(key)
                    guess_map.setdefault(key, []).append((c, country))
                else:
                    key = (r2["lat"], r2["lng"])
                    all_guess_coords.append(key)
                    guess_map.setdefault(key, []).append((c, country))

                c["rounds"] += 1
                c["team_scores"].append(team_score)
                c["team_distances"].append(team_distance)

                c["player_scores"][p1].append(score1)
                c["player_scores"][p2].append(score2)

                c["player_distances"][p1].append(dist1)
                c["player_distances"][p2].append(dist2)

                if score1 == 5000:
                    c["player_5ks"][p1] += 1
                    player_total_5ks[p1] += 1
                if score2 == 5000:
                    c["player_5ks"][p2] += 1
                    player_total_5ks[p2] += 1

                # Compute score diff for this round
                enemy_best = game["roundStats"][rn - 1]["enemyBestScore"]
                score_diff = team_score - enemy_best
                c["score_diffs"].append(score_diff)

                # Increment country win if our best guess beats the enemy
                if score_diff > 0:
                    c["wins"] += 1
    
    # unique coords
    unique_coords = list(set(all_guess_coords))
    results = rg.search(unique_coords)  # batch search

    # map results back
    for i, coord in enumerate(unique_coords):
        guess_country = results[i]['cc'].lower()
        entries = guess_map[coord]
        for c, actual_country in entries:
            c["total_guesses"] += 1
            if guess_country == actual_country.lower():
                c["correct_guesses"] += 1

    # Compute final aggregates 
    results = {}

    results["overall"] = {
        "total_games": total_games,
        "win_percentage": total_wins / total_games if total_games else 0,
        "avg_rounds_per_game": total_rounds / total_games if total_games else 0,
        "player_contribution_percent": {
            p: player_contrib[p] / player_rounds[p] if player_rounds[p] else 0
            for p in player_contrib
        },
        "avg_individual_score": {
            p: player_scores[p] / player_rounds[p] if player_rounds[p] else 0
            for p in player_scores
        },
        "player_total_5ks": dict(player_total_5ks),
        "avg_guess_time": {
            p: (player_total_time[p] / player_time_rounds[p])
            if player_time_rounds[p] else 0
            for p in player_total_time
        },

        "merchant_stats": merchant_stats,
    }

    # Country-level aggregates
    results["countries"] = {}
    for country, data in country_stats.items():
        results["countries"][country] = {
            "rounds": data["rounds"],
            "avg_team_score": sum(data["team_scores"]) / len(data["team_scores"]) if data["team_scores"] else 0,
            "avg_team_distance_km": sum(data["team_distances"]) / len(data["team_distances"]) / 1000 if data["team_distances"] else 0,
            "avg_player_score": {
                p: sum(scores) / len(scores) if scores else 0
                for p, scores in data["player_scores"].items()
            },
            "avg_player_distance_km": {
                p: sum(dists) / len(dists) / 1000 if dists else 0
                for p, dists in data["player_distances"].items()
            },
            "player_5k_rate": {
                p: data["player_5ks"][p] / len(data["player_scores"][p])
                if len(data["player_scores"][p]) else 0
                for p in data["player_scores"]
            },

            # country-level avg score diff
            "avg_score_diff": (
                sum(data["score_diffs"]) / len(data["score_diffs"])
                if data["score_diffs"] else 0
            ),
            "hit_rate": (
                data["correct_guesses"] / data["total_guesses"]
                if data["total_guesses"] else 0
            ),
            "win_rate": (data["wins"] / data["rounds"] if data["rounds"] else 0),
        }

    # sort by avg_score_diff 
    sorted_by_score_diff = sorted(
        results["countries"].items(),
        key=lambda x: x[1]["avg_score_diff"],
        reverse=True
    )

    results["countries"] = sorted_by_score_diff

    # Same filtering logic
    eligible = [item for item in sorted_by_score_diff if item[1]["rounds"] >= 20]

    results["top_10_countries"] = eligible[:10]
    results["bottom_10_countries"] = eligible[-10:]

    return results

def process_duels(games, mapsize=14916.862 * 1000):
    """Process solo duels games into statistics."""
    total_games = 0
    total_wins = 0
    total_rounds = 0
    merchant_stats = {
        "multi_merchant": 0,
        "reverse_merchant": 0
    }
    all_guess_coords = []
    guess_map = {}

    # Player totals
    total_score = 0
    total_distance = 0.0
    total_5ks = 0
    total_time = 0.0
    time_rounds = 0

    # Country stats
    country_stats = defaultdict(lambda: {
        "rounds": 0,
        "scores": [],
        "distances": [],
        "5ks": 0,
        "score_diffs": [],
        "correct_guesses": 0,
        "total_guesses": 0,
        "wins": 0,
    })

    for game in games:
        total_games += 1

        # Compute total health change for win/loss
        game_health_change = sum(r["totalHealthChange"] for r in game["roundStats"])
        won_game = game_health_change > -6000
        lost_game = game_health_change == -6000

        if won_game:
            total_wins += 1

        # Compute score diff for merchant stats
        my_total = game["playerStats"]["totalScore"]
        enemy_total = sum(r["enemyScore"] for r in game["roundStats"])
        score_diff = my_total - enemy_total

        if lost_game and score_diff > 0:
            merchant_stats["multi_merchant"] += 1
        if won_game and score_diff < 0:
            merchant_stats["reverse_merchant"] += 1

        num_rounds = len(game["roundStats"])
        total_rounds += num_rounds

        rounds_dict = {r["roundNumber"]: r for r in game["playerStats"]["rounds"]}
        round_stats_dict = {r["roundNumber"]: r for r in game["roundStats"]}

        for rn in range(1, num_rounds + 1):
            r = rounds_dict.get(rn)
            rs = round_stats_dict.get(rn)

            if r is None:
                score, dist, country, time_val = 0, mapsize, None, None
            else:
                score = r["score"]
                dist = r["distance"]
                country = r["country"]
                time_val = r.get("time")

            if country is None and rs:
                country = rs.get("country")

            total_score += score
            total_distance += dist

            if time_val is not None:
                total_time += time_val
                time_rounds += 1

            if score == 5000:
                total_5ks += 1

            if country is not None:
                country = country.lower()
                c = country_stats[country]

                # Track guess coordinates for hit rate
                if r is not None:
                    key = (r["lat"], r["lng"])
                    all_guess_coords.append(key)
                    guess_map.setdefault(key, []).append((c, country))

                c["rounds"] += 1
                c["scores"].append(score)
                c["distances"].append(dist)

                if score == 5000:
                    c["5ks"] += 1

                # Score diff for this round
                enemy_score = rs["enemyScore"] if rs else 0
                round_score_diff = score - enemy_score
                c["score_diffs"].append(round_score_diff)

                if round_score_diff > 0:
                    c["wins"] += 1

    # Batch reverse geocode for hit rate
    if all_guess_coords:
        unique_coords = list(set(all_guess_coords))
        geo_results = rg.search(unique_coords)

        for i, coord in enumerate(unique_coords):
            guess_country = geo_results[i]['cc'].lower()
            entries = guess_map[coord]
            for c, actual_country in entries:
                c["total_guesses"] += 1
                if guess_country == actual_country.lower():
                    c["correct_guesses"] += 1

    # Compute final aggregates
    results = {}

    results["overall"] = {
        "total_games": total_games,
        "win_percentage": total_wins / total_games if total_games else 0,
        "avg_rounds_per_game": total_rounds / total_games if total_games else 0,
        "avg_score": total_score / total_rounds if total_rounds else 0,
        "total_5ks": total_5ks,
        "avg_guess_time": total_time / time_rounds if time_rounds else 0,
        "merchant_stats": merchant_stats,
    }

    # Country-level aggregates
    results["countries"] = {}
    for country, data in country_stats.items():
        results["countries"][country] = {
            "rounds": data["rounds"],
            "avg_score": sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0,
            "avg_distance_km": sum(data["distances"]) / len(data["distances"]) / 1000 if data["distances"] else 0,
            "5k_rate": data["5ks"] / data["rounds"] if data["rounds"] else 0,
            "avg_score_diff": sum(data["score_diffs"]) / len(data["score_diffs"]) if data["score_diffs"] else 0,
            "hit_rate": data["correct_guesses"] / data["total_guesses"] if data["total_guesses"] else 0,
            "win_rate": data["wins"] / data["rounds"] if data["rounds"] else 0,
        }

    # Sort by avg_score_diff
    sorted_by_score_diff = sorted(
        results["countries"].items(),
        key=lambda x: x[1]["avg_score_diff"],
        reverse=True
    )

    results["countries"] = sorted_by_score_diff

    # Top/bottom 10 with minimum 20 rounds
    eligible = [item for item in sorted_by_score_diff if item[1]["rounds"] >= 20]
    results["top_10_countries"] = eligible[:10]
    results["bottom_10_countries"] = eligible[-10:]

    return results


if __name__ == "__main__":
    input_file = "data/games.json"
    output_file = "data/processed_stats.json"

    games = load_data(input_file)
    stats = process_games(games)

    save_json(output_file, stats)

    print(f"Stats saved to {output_file}")