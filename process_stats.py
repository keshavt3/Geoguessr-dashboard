import json
from collections import defaultdict

def load_data(path):
    with open(path, "r") as f:
        return json.load(f)

def process_games(games, mapsize=14916.862 * 1000):  # mapsize in meters, default is world map diagonal
    # Overall stats
    total_games = 0
    total_wins = 0
    total_rounds = 0

    # Contribution counts
    player_contrib = defaultdict(int)
    player_rounds = defaultdict(int)

    # Per-player totals
    player_scores = defaultdict(int)
    player_distances = defaultdict(float)
    player_total_5ks = defaultdict(int)

    # Country stats
    country_stats = defaultdict(lambda: {
        "rounds": 0,
        "team_scores": [],
        "player_scores": defaultdict(list),
        "team_distances": [],
        "player_distances": defaultdict(list),
        "player_5ks": defaultdict(int),
    })

    for game in games:
        total_games += 1

        # Win/loss
        if game["teamStats"]["totalHealthChange"] > -6000:
            total_wins += 1

        # Player IDs (assuming 2 players)
        players = list(game["playerStats"].keys())
        p1, p2 = players[0], players[1]

        rounds_p1 = game["playerStats"][p1]["rounds"]
        rounds_p2 = game["playerStats"][p2]["rounds"]

        # Preprocess rounds into dicts for O(1) lookup
        rounds_dict_p1 = {r["roundNumber"]: r for r in rounds_p1}
        rounds_dict_p2 = {r["roundNumber"]: r for r in rounds_p2}

        # Total rounds from roundStats
        num_rounds = game["roundStats"][-1]["roundNumber"]
        total_rounds += num_rounds

        for rn in range(1, num_rounds + 1):
            r1 = rounds_dict_p1.get(rn)
            r2 = rounds_dict_p2.get(rn)

            # Handle missing rounds
            if r1 is None:
                score1, dist1, country = 0, mapsize, None
            else:
                score1, dist1, country = r1["score"], r1["distance"], r1["country"]

            if r2 is None:
                score2, dist2, _ = 0, mapsize, None
            else:
                score2, dist2, _ = r2["score"], r2["distance"], r2["country"]

            # Country: pick whichever exists
            if country is None and r2 is not None:
                country = r2["country"]

            # Best team score and distance
            team_score = max(score1, score2)
            team_distance = min(dist1, dist2)

            # Update player totals
            player_scores[p1] += score1
            player_scores[p2] += score2
            player_distances[p1] += dist1
            player_distances[p2] += dist2

            # Contribution (who was closer)
            if dist1 < dist2:
                player_contrib[p1] += 1
            elif dist2 < dist1:
                player_contrib[p2] += 1

            player_rounds[p1] += 1
            player_rounds[p2] += 1

            # ---- Country Stats ----
            if country is not None:
                country = country.lower()
                c = country_stats[country]
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

    # ------- Compute final aggregates -------
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
        "player_total_5ks": dict(player_total_5ks)
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
            }
        }

    sorted_by_team_score = sorted(
        results["countries"].items(),
        key=lambda x: x[1]["avg_team_score"],
        reverse = True
    )

    results["countries"] = sorted_by_team_score

    # Filter in place for top/bottom 10 with at least 20 rounds
    eligible = [item for item in sorted_by_team_score if item[1]["rounds"] >= 20]

    results["top_10_countries"] = eligible[:10]         # first 10 best
    results["bottom_10_countries"] = eligible[-10:]     # last 10 worst

    return results

def main():
    input_file = "team_duels_stats.json"
    output_file = "processed_stats.json"

    games = load_data(input_file)
    stats = process_games(games)

    # Save results to a JSON file
    with open(output_file, "w") as f:
        json.dump(stats, f, indent=4)

    print(f"Stats saved to {output_file}")

if __name__ == "__main__":
    main()