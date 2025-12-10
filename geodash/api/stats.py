"""REST API for GeoGuessr Dashboard statistics."""
import flask
import requests
import geodash
from geodash.model import get_db
from geoguessr.fetch_games import fetch_filtered_tokens, fetch_duels, fetch_team_duels
from geoguessr.process_stats import process_duels, process_games
from geoguessr.utils import save_json, load_data as load_json


@geodash.app.route('/api/v1/stats/', methods=['GET'])
def get_stats():
    """Return processed stats overview."""
    db = get_db()

    # Get the most recent overall stats
    cur = db.execute(
        "SELECT * FROM overall_stats ORDER BY created_at DESC LIMIT 1"
    )
    overall = cur.fetchone()

    if overall is None:
        return flask.jsonify({"success": False, "error": "No stats found"}), 404

    # Get player contributions if team duels
    contributions = []
    if overall['game_type'] == 'team_duels':
        cur = db.execute(
            "SELECT * FROM player_contributions WHERE overall_stats_id = ?",
            (overall['id'],)
        )
        contributions = cur.fetchall()

    return flask.jsonify({
        "success": True,
        "data": {
            "overall": overall,
            "player_contributions": contributions
        }
    })


@geodash.app.route('/api/v1/countries/', methods=['GET'])
def get_countries():
    """Return per-country statistics."""
    db = get_db()

    # Get the most recent overall stats id
    cur = db.execute(
        "SELECT id FROM overall_stats ORDER BY created_at DESC LIMIT 1"
    )
    row = cur.fetchone()

    if row is None:
        return flask.jsonify({"success": False, "error": "No stats found"}), 404

    overall_id = row['id']

    # Get all country stats sorted by avg_score_diff
    cur = db.execute(
        """SELECT * FROM country_stats
           WHERE overall_stats_id = ?
           ORDER BY avg_score_diff DESC""",
        (overall_id,)
    )
    countries = cur.fetchall()

    # Filter for top/bottom 10 with minimum 20 rounds
    eligible = [c for c in countries if c['rounds'] >= 20]

    return flask.jsonify({
        "success": True,
        "data": {
            "all_countries": countries,
            "top_10": eligible[:10],
            "bottom_10": eligible[-10:] if len(eligible) >= 10 else eligible
        }
    })


@geodash.app.route('/api/v1/fetch-latest/', methods=['POST'])
def fetch_latest():
    """Fetch latest duels games for a player."""
    data = flask.request.get_json()

    if not data or 'playerId' not in data:
        return flask.jsonify({"success": False, "error": "playerId is required"}), 400
    if 'ncfa' not in data:
        return flask.jsonify({"success": False, "error": "ncfa is required"}), 400

    player_id = data['playerId']
    ncfa = data['ncfa']
    mode_filter = data.get('modeFilter', 'all')  # 'all', 'competitive', 'casual'

    try:
        # Create authenticated session
        session = requests.Session()
        session.cookies.set("_ncfa", ncfa, domain="www.geoguessr.com")
        session.cookies.set("_ncfa", ncfa, domain="game-server.geoguessr.com")

        # Always fetch ALL game IDs (mode info is stored with each game)
        all_game_ids_with_mode = fetch_filtered_tokens(session, game_type="duels", mode_filter="all")

        if not all_game_ids_with_mode:
            return flask.jsonify({"success": False, "error": "No games found in feed"}), 404

        # Filter out already-fetched games
        db = get_db()
        cur = db.execute(
            "SELECT game_id FROM fetched_games WHERE player_id = ? AND game_type = ?",
            (player_id, 'duels')
        )
        existing_ids = {row['game_id'] for row in cur.fetchall()}
        new_game_ids_with_mode = {
            gid: mode for gid, mode in all_game_ids_with_mode.items()
            if gid not in existing_ids
        }

        # Fetch only new games (if any)
        if new_game_ids_with_mode:
            new_games = fetch_duels(session, new_game_ids_with_mode, player_id)

            # Record fetched game IDs
            for game in new_games:
                db.execute(
                    "INSERT OR IGNORE INTO fetched_games (game_id, player_id, game_type) VALUES (?, ?, ?)",
                    (game['gameId'], player_id, 'duels')
                )
        else:
            new_games = []

        # Load existing games and merge
        try:
            existing_games = load_json("data/games.json")
        except Exception:
            existing_games = []

        all_games = existing_games + new_games
        save_json("data/games.json", all_games)

        # Apply mode filter for processing
        if mode_filter == 'competitive':
            filtered_games = [g for g in all_games if g.get('isCompetitive', False)]
        elif mode_filter == 'casual':
            filtered_games = [g for g in all_games if not g.get('isCompetitive', False)]
        else:
            filtered_games = all_games

        # Process filtered games
        stats = process_duels(filtered_games)

        # Save to database
        _save_stats_to_db(player_id, 'duels', stats)

        return flask.jsonify({
            "success": True,
            "games_fetched": len(new_games),
            "total_games": len(all_games),
            "filtered_games": len(filtered_games),
            "mode_filter": mode_filter
        })

    except Exception as e:
        return flask.jsonify({"success": False, "error": str(e)}), 500


@geodash.app.route('/api/v1/fetch-team-duels/', methods=['POST'])
def fetch_team_duels_api():
    """Fetch latest team duels games."""
    data = flask.request.get_json()

    if not data or 'playerId' not in data:
        return flask.jsonify({"success": False, "error": "playerId is required"}), 400
    if 'ncfa' not in data:
        return flask.jsonify({"success": False, "error": "ncfa is required"}), 400

    player_id = data['playerId']
    ncfa = data['ncfa']
    teammate_id = data.get('teammateId')
    mode_filter = data.get('modeFilter', 'all')  # 'all', 'competitive', 'casual'

    try:
        # Create authenticated session
        session = requests.Session()
        session.cookies.set("_ncfa", ncfa, domain="www.geoguessr.com")
        session.cookies.set("_ncfa", ncfa, domain="game-server.geoguessr.com")

        # Always fetch ALL game IDs (mode info is stored with each game)
        all_game_ids_with_mode = fetch_filtered_tokens(session, game_type="team", mode_filter="all")

        if not all_game_ids_with_mode:
            return flask.jsonify({"success": False, "error": "No games found in feed"}), 404

        # Filter out already-fetched games
        db = get_db()
        cur = db.execute(
            "SELECT game_id FROM fetched_games WHERE player_id = ? AND game_type = ?",
            (player_id, 'team_duels')
        )
        existing_ids = {row['game_id'] for row in cur.fetchall()}
        new_game_ids_with_mode = {
            gid: mode for gid, mode in all_game_ids_with_mode.items()
            if gid not in existing_ids
        }

        # Fetch only new games
        if new_game_ids_with_mode:
            new_games = fetch_team_duels(session, new_game_ids_with_mode, player_id, teammate_id)

            # Record ALL fetched game IDs
            for gid in new_game_ids_with_mode.keys():
                db.execute(
                    "INSERT OR IGNORE INTO fetched_games (game_id, player_id, game_type) VALUES (?, ?, ?)",
                    (gid, player_id, 'team_duels')
                )
        else:
            new_games = []

        # Load existing games
        try:
            existing_games = load_json("data/team_games.json")
        except Exception:
            existing_games = []

        # Merge all games
        all_games = existing_games + new_games
        save_json("data/team_games.json", all_games)

        # Apply filters for processing
        filtered_games = all_games

        # Mode filter
        if mode_filter == 'competitive':
            filtered_games = [g for g in filtered_games if g.get('isCompetitive', False)]
        elif mode_filter == 'casual':
            filtered_games = [g for g in filtered_games if not g.get('isCompetitive', False)]

        # Teammate filter
        if teammate_id:
            filtered_games = [
                g for g in filtered_games
                if any(pid == teammate_id for pid in g.get('playerStats', {}).keys())
            ]

        # Process filtered games
        stats = process_games(filtered_games)

        # Save to database
        _save_stats_to_db(player_id, 'team_duels', stats)

        return flask.jsonify({
            "success": True,
            "games_fetched": len(new_games),
            "total_games": len(all_games),
            "filtered_games": len(filtered_games),
            "mode_filter": mode_filter,
            "teammate_filter": teammate_id
        })

    except Exception as e:
        return flask.jsonify({"success": False, "error": str(e)}), 500


def _save_stats_to_db(player_id, game_type, stats):
    """Save processed stats to the database."""
    db = get_db()

    overall = stats['overall']

    # Insert overall stats
    if game_type == 'duels':
        cur = db.execute(
            """INSERT INTO overall_stats
               (player_id, game_type, total_games, win_percentage, avg_rounds_per_game,
                avg_score, total_5ks, avg_guess_time, multi_merchant, reverse_merchant)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (player_id, game_type, overall['total_games'], overall['win_percentage'],
             overall['avg_rounds_per_game'], overall.get('avg_score'),
             overall.get('total_5ks'), overall.get('avg_guess_time'),
             overall['merchant_stats']['multi_merchant'],
             overall['merchant_stats']['reverse_merchant'])
        )
    else:
        # Team duels
        cur = db.execute(
            """INSERT INTO overall_stats
               (player_id, game_type, total_games, win_percentage, avg_rounds_per_game,
                multi_merchant, reverse_merchant)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (player_id, game_type, overall['total_games'], overall['win_percentage'],
             overall['avg_rounds_per_game'],
             overall['merchant_stats']['multi_merchant'],
             overall['merchant_stats']['reverse_merchant'])
        )

    overall_id = cur.lastrowid

    # Insert player contributions (for team duels)
    if game_type == 'team_duels':
        for pid, contrib in overall.get('player_contribution_percent', {}).items():
            db.execute(
                """INSERT INTO player_contributions
                   (overall_stats_id, player_id, contribution_percent, avg_individual_score,
                    total_5ks, avg_guess_time)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (overall_id, pid, contrib,
                 overall.get('avg_individual_score', {}).get(pid),
                 overall.get('player_total_5ks', {}).get(pid),
                 overall.get('avg_guess_time', {}).get(pid))
            )

    # Insert country stats
    # stats['countries'] is a list of tuples: (country_code, stats_dict)
    for country_code, cstats in stats.get('countries', []):
        db.execute(
            """INSERT INTO country_stats
               (overall_stats_id, country_code, rounds, avg_score, avg_distance_km,
                five_k_rate, avg_score_diff, hit_rate, win_rate)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (overall_id, country_code, cstats['rounds'],
             cstats.get('avg_score') or cstats.get('avg_team_score', 0),
             cstats.get('avg_distance_km') or cstats.get('avg_team_distance_km', 0),
             cstats.get('5k_rate') or 0,
             cstats['avg_score_diff'], cstats['hit_rate'], cstats['win_rate'])
        )

    db.commit()
