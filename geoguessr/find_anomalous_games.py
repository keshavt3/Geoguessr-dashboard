#!/usr/bin/env python3
"""Find anomalous team duel games where the player has 0 rounds or is missing."""

import json
import sys

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def find_anomalous_games(games_path, my_player_id=None):
    games = load_json(games_path)

    print(f"Total games loaded: {len(games)}\n")

    # Track all player IDs and their game counts
    player_game_counts = {}
    player_round_counts = {}

    anomalous_games = []

    for i, game in enumerate(games):
        game_id = game.get('gameId', f'unknown_{i}')
        player_stats = game.get('playerStats', {})

        # Count games and rounds per player
        for pid, stats in player_stats.items():
            player_game_counts[pid] = player_game_counts.get(pid, 0) + 1
            rounds = len(stats.get('rounds', []))
            player_round_counts[pid] = player_round_counts.get(pid, 0) + rounds

        # Check for anomalies
        anomalies = []

        # Check if any player has 0 rounds
        for pid, stats in player_stats.items():
            rounds = stats.get('rounds', [])
            if len(rounds) == 0:
                anomalies.append(f"Player {pid} has 0 rounds")

        # Check if there are not exactly 2 players
        if len(player_stats) != 2:
            anomalies.append(f"Game has {len(player_stats)} players instead of 2")

        # Check if my_player_id is specified and not in the game
        if my_player_id and my_player_id not in player_stats:
            anomalies.append(f"Your player ID ({my_player_id}) not found in playerStats")

        if anomalies:
            anomalous_games.append({
                'game_id': game_id,
                'index': i,
                'players': list(player_stats.keys()),
                'rounds_per_player': {pid: len(stats.get('rounds', [])) for pid, stats in player_stats.items()},
                'anomalies': anomalies
            })

    # Print results
    print("=" * 60)
    print("PLAYER STATISTICS")
    print("=" * 60)

    # Sort by game count
    sorted_players = sorted(player_game_counts.items(), key=lambda x: x[1], reverse=True)

    for pid, count in sorted_players:
        rounds = player_round_counts.get(pid, 0)
        avg_rounds = rounds / count if count > 0 else 0
        marker = " <-- YOU" if pid == my_player_id else ""
        print(f"  {pid}: {count} games, {rounds} total rounds, {avg_rounds:.1f} avg rounds/game{marker}")

    print(f"\nTotal unique players: {len(player_game_counts)}")

    # Find players with suspiciously low game counts
    print("\n" + "=" * 60)
    print("PLAYERS WITH VERY FEW GAMES (potential anomalies)")
    print("=" * 60)

    low_game_players = [(pid, count) for pid, count in sorted_players if count <= 5]
    if low_game_players:
        for pid, count in low_game_players:
            rounds = player_round_counts.get(pid, 0)
            print(f"  {pid}: {count} games, {rounds} total rounds")
    else:
        print("  None found")

    print("\n" + "=" * 60)
    print(f"ANOMALOUS GAMES ({len(anomalous_games)} found)")
    print("=" * 60)

    if anomalous_games:
        for ag in anomalous_games:
            print(f"\nGame ID: {ag['game_id']}")
            print(f"  Index in array: {ag['index']}")
            print(f"  Players: {ag['players']}")
            print(f"  Rounds per player: {ag['rounds_per_player']}")
            print(f"  Anomalies:")
            for anomaly in ag['anomalies']:
                print(f"    - {anomaly}")
    else:
        print("  No anomalous games found")

    return anomalous_games, player_game_counts

if __name__ == "__main__":
    games_path = "data/team_games.json"

    # Optionally pass your player ID as argument
    my_player_id = sys.argv[1] if len(sys.argv) > 1 else None

    if my_player_id:
        print(f"Looking for anomalies with your player ID: {my_player_id}\n")
    else:
        print("Tip: Pass your player ID as argument to see if you're missing from any games")
        print(f"Usage: python {sys.argv[0]} YOUR_PLAYER_ID\n")

    find_anomalous_games(games_path, my_player_id)
