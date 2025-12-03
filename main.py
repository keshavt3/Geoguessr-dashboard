from geoguessr.fetch_games import fetch_filtered_tokens, fetch_team_duels
from geoguessr.process_stats import process_games
from geoguessr.utils import load_data, save_json
import requests

def main():
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
    game_tokens = fetch_filtered_tokens(session, game_type=game_type, mode_filter=mode_filter)
    games = fetch_team_duels(session, game_tokens, player_id, teammate_id)

    save_json("data/games.json", games)

    print(f"Saved {len(games)} games.")

    input_file = "data/games.json"
    output_file = "data/processed_stats.json"

    games = load_data(input_file)
    stats = process_games(games)

    save_json(output_file, stats)

    print(f"Stats saved to {output_file}")

if __name__ == "__main__":
    main()