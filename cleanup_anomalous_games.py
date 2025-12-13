#!/usr/bin/env python3
"""Remove anomalous games from team_games.json that don't match standard 2v2 format."""

import json

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def cleanup_games(games_path):
    games = load_json(games_path)
    original_count = len(games)

    valid_games = []
    removed_games = []

    for game in games:
        game_id = game.get('gameId', 'unknown')
        player_stats = game.get('playerStats', {})
        players = list(player_stats.keys())

        # Check if this is a valid 2-player team game
        if len(players) != 2:
            removed_games.append({
                'game_id': game_id,
                'reason': f'Invalid player count: {len(players)}',
                'players': players
            })
            continue

        # Check if any player has 0 rounds (joined but never played)
        has_zero_rounds = False
        for pid, stats in player_stats.items():
            if len(stats.get('rounds', [])) == 0:
                removed_games.append({
                    'game_id': game_id,
                    'reason': f'Player {pid} has 0 rounds',
                    'players': players
                })
                has_zero_rounds = True
                break

        if not has_zero_rounds:
            valid_games.append(game)

    print(f"Original games: {original_count}")
    print(f"Valid games: {len(valid_games)}")
    print(f"Removed games: {len(removed_games)}")

    if removed_games:
        print("\nRemoved games:")
        for rg in removed_games:
            print(f"  - {rg['game_id']}: {rg['reason']}")

    # Backup original and save cleaned version
    if removed_games:
        backup_path = games_path.replace('.json', '_backup.json')
        save_json(backup_path, games)
        print(f"\nBackup saved to: {backup_path}")

        save_json(games_path, valid_games)
        print(f"Cleaned data saved to: {games_path}")
    else:
        print("\nNo changes needed.")

    return valid_games, removed_games

if __name__ == "__main__":
    cleanup_games("data/team_games.json")
