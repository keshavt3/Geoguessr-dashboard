"""REST API for GeoGuessr Dashboard statistics."""
import time
import flask
import requests
import geodash
from geodash.model import get_db
from geoguessr.fetch_games import (
    fetch_filtered_tokens, fetch_duels, fetch_team_duels,
    fetch_single_duel, fetch_single_team_duel,
    AuthenticationError, InvalidPlayerIdError
)
from geoguessr.process_stats import process_duels, process_games
from geoguessr.utils import save_json, load_data as load_json


def _fetch_username(session, player_id):
    """Fetch username for a player ID from GeoGuessr API and cache it."""
    db = get_db()

    # Check cache first
    cur = db.execute("SELECT username FROM player_names WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    if row:
        return row['username']

    # Fetch from API
    try:
        resp = session.get(f"https://www.geoguessr.com/api/v3/users/{player_id}")
        if resp.status_code == 200:
            data = resp.json()
            username = data.get('nick') or data.get('name') or player_id
        else:
            username = player_id  # Fallback to ID if API fails
    except Exception:
        username = player_id

    # Cache the result
    db.execute(
        "INSERT OR REPLACE INTO player_names (player_id, username) VALUES (?, ?)",
        (player_id, username)
    )
    db.commit()

    time.sleep(0.1)  # Rate limiting
    return username


def _get_username(player_id):
    """Get cached username for a player ID."""
    db = get_db()
    cur = db.execute("SELECT username FROM player_names WHERE player_id = ?", (player_id,))
    row = cur.fetchone()
    return row['username'] if row else player_id


@geodash.app.route('/api/v1/teammates/', methods=['GET'])
def get_teammates():
    """Return list of all teammates with usernames and game counts."""
    db = get_db()

    # Get the main player_id (the user) from overall_stats
    cur = db.execute(
        """SELECT player_id FROM overall_stats
           WHERE filter_type = 'team_duels_all'
           ORDER BY created_at DESC LIMIT 1"""
    )
    row = cur.fetchone()
    main_player_id = row['player_id'] if row else None

    # Get all player contributions with game counts
    cur = db.execute(
        """SELECT pc.player_id, pc.games_played, pn.username
           FROM player_contributions pc
           LEFT JOIN player_names pn ON pc.player_id = pn.player_id
           JOIN overall_stats os ON pc.overall_stats_id = os.id
           WHERE os.filter_type = 'team_duels_all'
           ORDER BY os.created_at DESC"""
    )
    rows = cur.fetchall()

    # Deduplicate by player_id (keep first occurrence which is most recent)
    # Exclude the main player (can't be teammate with yourself)
    seen = set()
    teammates = []
    for row in rows:
        if row['player_id'] not in seen and row['player_id'] != main_player_id:
            seen.add(row['player_id'])
            teammates.append({
                'player_id': row['player_id'],
                'username': row['username'] or row['player_id'],
                'games_played': row['games_played'] or 0
            })

    # Sort by games played descending
    teammates.sort(key=lambda x: x['games_played'], reverse=True)

    return flask.jsonify({
        "success": True,
        "teammates": teammates
    })


@geodash.app.route('/api/v1/stats/', methods=['GET'])
def get_stats():
    """Return processed stats overview.

    Query params:
        game_type: 'duels' or 'team_duels' (default: 'duels')
        mode: 'all', 'competitive', or 'casual' (default: 'all')
        teammate: optional player_id to filter team stats by teammate
    """
    db = get_db()

    game_type = flask.request.args.get('game_type', 'duels')
    mode = flask.request.args.get('mode', 'all')
    teammate = flask.request.args.get('teammate', '')
    filter_type = f"{game_type}_{mode}"

    # If teammate filter is set, recompute stats from JSON
    if teammate and game_type == 'team_duels':
        try:
            all_team = load_json("data/team_games.json")
        except Exception:
            return flask.jsonify({"success": False, "error": "No team games found"}), 404

        # Filter games by teammate
        filtered_games = [
            g for g in all_team
            if teammate in g.get('playerStats', {}).keys()
        ]

        # Apply mode filter
        if mode == 'competitive':
            filtered_games = [g for g in filtered_games if g.get('isCompetitive', False)]
        elif mode == 'casual':
            filtered_games = [g for g in filtered_games if not g.get('isCompetitive', False)]

        if not filtered_games:
            return flask.jsonify({"success": False, "error": "No games found with this teammate"}), 404

        # Process filtered games
        stats = process_games(filtered_games)
        overall = stats['overall']

        # Build contributions with usernames
        contributions = []
        for pid, contrib in overall.get('player_contribution_percent', {}).items():
            contributions.append({
                'player_id': pid,
                'username': _get_username(pid),
                'contribution_percent': contrib,
                'avg_individual_score': overall.get('avg_individual_score', {}).get(pid),
                'total_5ks': overall.get('player_total_5ks', {}).get(pid),
                'avg_guess_time': overall.get('avg_guess_time', {}).get(pid),
                'games_played': overall.get('games_per_player', {}).get(pid, 0)
            })

        return flask.jsonify({
            "success": True,
            "data": {
                "overall": {
                    "total_games": overall['total_games'],
                    "win_percentage": overall['win_percentage'],
                    "avg_rounds_per_game": overall['avg_rounds_per_game'],
                    "multi_merchant": overall['merchant_stats']['multi_merchant'],
                    "reverse_merchant": overall['merchant_stats']['reverse_merchant'],
                    "game_type": "team_duels",
                    "filter_type": f"team_duels_{mode}_teammate"
                },
                "player_contributions": contributions
            }
        })

    # Standard database lookup
    cur = db.execute(
        "SELECT * FROM overall_stats WHERE filter_type = ? ORDER BY created_at DESC LIMIT 1",
        (filter_type,)
    )
    overall = cur.fetchone()

    if overall is None:
        return flask.jsonify({"success": False, "error": f"No stats found for {filter_type}"}), 404

    # Get player contributions if team duels, with usernames
    contributions = []
    if overall['game_type'] == 'team_duels':
        cur = db.execute(
            """SELECT pc.*, pn.username
               FROM player_contributions pc
               LEFT JOIN player_names pn ON pc.player_id = pn.player_id
               WHERE pc.overall_stats_id = ?""",
            (overall['id'],)
        )
        rows = cur.fetchall()
        for row in rows:
            contributions.append({
                'player_id': row['player_id'],
                'username': row['username'] or row['player_id'],
                'contribution_percent': row['contribution_percent'],
                'avg_individual_score': row['avg_individual_score'],
                'total_5ks': row['total_5ks'],
                'avg_guess_time': row['avg_guess_time'],
                'games_played': row['games_played'] or 0
            })

    return flask.jsonify({
        "success": True,
        "data": {
            "overall": dict(overall),
            "player_contributions": contributions
        }
    })


@geodash.app.route('/api/v1/countries/', methods=['GET'])
def get_countries():
    """Return per-country statistics.

    Query params:
        game_type: 'duels' or 'team_duels' (default: 'duels')
        mode: 'all', 'competitive', or 'casual' (default: 'all')
        teammate: optional player_id to filter team stats by teammate
        sort: 'score_diff', 'avg_score', 'win_rate', or 'hit_rate' (default: 'score_diff')
    """
    db = get_db()

    game_type = flask.request.args.get('game_type', 'duels')
    mode = flask.request.args.get('mode', 'all')
    teammate = flask.request.args.get('teammate', '')
    sort_by = flask.request.args.get('sort', 'score_diff')
    filter_type = f"{game_type}_{mode}"

    # Map sort parameter to field name
    sort_field_map = {
        'score_diff': 'avg_score_diff',
        'avg_score': 'avg_score',
        'win_rate': 'win_rate',
        'hit_rate': 'hit_rate'
    }
    sort_field = sort_field_map.get(sort_by, 'avg_score_diff')

    # If teammate filter is set, recompute stats from JSON
    if teammate and game_type == 'team_duels':
        try:
            all_team = load_json("data/team_games.json")
        except Exception:
            return flask.jsonify({"success": False, "error": "No team games found"}), 404

        # Filter games by teammate
        filtered_games = [
            g for g in all_team
            if teammate in g.get('playerStats', {}).keys()
        ]

        # Apply mode filter
        if mode == 'competitive':
            filtered_games = [g for g in filtered_games if g.get('isCompetitive', False)]
        elif mode == 'casual':
            filtered_games = [g for g in filtered_games if not g.get('isCompetitive', False)]

        if not filtered_games:
            return flask.jsonify({"success": False, "error": "No games found with this teammate"}), 404

        # Process filtered games
        stats = process_games(filtered_games)

        # Convert countries list to expected format
        countries = []
        for country_code, cstats in stats.get('countries', []):
            countries.append({
                'country_code': country_code,
                'rounds': cstats['rounds'],
                'avg_score': cstats.get('avg_team_score', 0),
                'avg_distance_km': cstats.get('avg_team_distance_km', 0),
                'five_k_rate': cstats.get('5k_rate', 0),
                'avg_score_diff': cstats['avg_score_diff'],
                'hit_rate': cstats['hit_rate'],
                'win_rate': cstats['win_rate']
            })

        # Sort countries by the specified field
        countries.sort(key=lambda c: c.get(sort_field, 0), reverse=True)
        eligible = [c for c in countries if c['rounds'] >= 20]

        return flask.jsonify({
            "success": True,
            "data": {
                "all_countries": countries,
                "top_10": eligible[:10],
                "bottom_10": eligible[-10:] if len(eligible) >= 10 else eligible
            }
        })

    # Standard database lookup
    cur = db.execute(
        "SELECT id FROM overall_stats WHERE filter_type = ? ORDER BY created_at DESC LIMIT 1",
        (filter_type,)
    )
    row = cur.fetchone()

    if row is None:
        return flask.jsonify({"success": False, "error": f"No stats found for {filter_type}"}), 404

    overall_id = row['id']

    # Fetch all countries and sort in Python (safer than dynamic SQL)
    cur = db.execute(
        """SELECT * FROM country_stats
           WHERE overall_stats_id = ?""",
        (overall_id,)
    )
    countries = [dict(row) for row in cur.fetchall()]

    # Sort by the specified field
    countries.sort(key=lambda c: c.get(sort_field, 0), reverse=True)

    eligible = [c for c in countries if c['rounds'] >= 20]

    return flask.jsonify({
        "success": True,
        "data": {
            "all_countries": countries,
            "top_10": eligible[:10],
            "bottom_10": eligible[-10:] if len(eligible) >= 10 else eligible
        }
    })


@geodash.app.route('/api/v1/countries/<country_code>/details/', methods=['GET'])
def get_country_details(country_code):
    """Return detailed analytics for a specific country.

    Query params:
        game_type: 'duels' or 'team_duels' (default: 'team_duels')
        mode: 'all', 'competitive', or 'casual' (default: 'all')
        teammate: optional player_id to filter team stats by teammate

    Returns:
        - heatmap_data: actual and guess coordinates for all rounds
        - wrong_guesses: most common incorrectly guessed countries
        - distance_distribution: breakdown of guess distances
        - region_stats: performance by region within the country
    """
    import reverse_geocoder as rg

    game_type = flask.request.args.get('game_type', 'team_duels')
    mode = flask.request.args.get('mode', 'all')
    teammate = flask.request.args.get('teammate', '')

    country_code = country_code.lower()

    # Load appropriate game data
    try:
        if game_type == 'team_duels':
            games = load_json("data/team_games.json")
        else:
            games = load_json("data/games.json")
    except Exception:
        return flask.jsonify({"success": False, "error": "No games found"}), 404

    # Apply filters
    if mode == 'competitive':
        games = [g for g in games if g.get('isCompetitive', False)]
    elif mode == 'casual':
        games = [g for g in games if not g.get('isCompetitive', False)]

    if teammate and game_type == 'team_duels':
        games = [g for g in games if teammate in g.get('playerStats', {}).keys()]

    # Collect all rounds for this country
    rounds_data = []

    for game in games:
        # Build a lookup for round stats (enemy scores)
        round_stats_lookup = {}
        for rs in game.get('roundStats', []):
            rn = rs.get('roundNumber')
            if game_type == 'team_duels':
                round_stats_lookup[rn] = rs.get('enemyBestScore', 0)
            else:
                round_stats_lookup[rn] = rs.get('enemyScore', 0)

        if game_type == 'team_duels':
            # For team duels, find the best score per round across players
            best_scores_per_round = {}
            for player_id, player_stats in game.get('playerStats', {}).items():
                for round_data in player_stats.get('rounds', []):
                    rn = round_data.get('roundNumber')
                    score = round_data.get('score', 0)
                    if rn not in best_scores_per_round or score > best_scores_per_round[rn]['score']:
                        best_scores_per_round[rn] = {
                            'distance': round_data.get('distance', 0),
                            'score': score,
                            'guessLat': round_data.get('lat'),
                            'guessLng': round_data.get('lng'),
                            'actualLat': round_data.get('actualLat'),
                            'actualLng': round_data.get('actualLng'),
                            'time': round_data.get('time'),
                            'country': round_data.get('country', ''),
                            'enemyScore': round_stats_lookup.get(rn, 0)
                        }
            # Add rounds matching this country
            for rn, rd in best_scores_per_round.items():
                if rd['country'].lower() == country_code:
                    rounds_data.append(rd)
        else:
            for round_data in game.get('playerStats', {}).get('rounds', []):
                if round_data.get('country', '').lower() == country_code:
                    rn = round_data.get('roundNumber')
                    rounds_data.append({
                        'distance': round_data.get('distance', 0),
                        'score': round_data.get('score', 0),
                        'guessLat': round_data.get('lat'),
                        'guessLng': round_data.get('lng'),
                        'actualLat': round_data.get('actualLat'),
                        'actualLng': round_data.get('actualLng'),
                        'time': round_data.get('time'),
                        'enemyScore': round_stats_lookup.get(rn, 0)
                    })

    if not rounds_data:
        return flask.jsonify({"success": False, "error": "No rounds found for this country"}), 404

    # 1. Heatmap data - actual and guess coordinates
    heatmap_data = {
        'actual': [],
        'guess': []
    }
    for r in rounds_data:
        if r['actualLat'] is not None and r['actualLng'] is not None:
            heatmap_data['actual'].append({'lat': r['actualLat'], 'lng': r['actualLng']})
        if r['guessLat'] is not None and r['guessLng'] is not None:
            heatmap_data['guess'].append({'lat': r['guessLat'], 'lng': r['guessLng']})

    # 2. Wrong guess countries - reverse geocode guess coordinates
    wrong_guesses = {}
    guess_coords = [(r['guessLat'], r['guessLng']) for r in rounds_data
                    if r['guessLat'] is not None and r['guessLng'] is not None]

    if guess_coords:
        try:
            geo_results = rg.search(guess_coords)
            for i, result in enumerate(geo_results):
                guessed_country = result['cc'].lower()
                if guessed_country != country_code:
                    wrong_guesses[guessed_country] = wrong_guesses.get(guessed_country, 0) + 1
        except Exception as e:
            print(f"Reverse geocoding error: {e}")

    # Sort wrong guesses by frequency
    wrong_guesses_list = sorted(
        [{'country': k, 'count': v} for k, v in wrong_guesses.items()],
        key=lambda x: x['count'],
        reverse=True
    )[:10]  # Top 10

    # 3. Distance distribution
    distances = [r['distance'] for r in rounds_data]
    distance_buckets = {
        '0-100m': 0,
        '100m-1km': 0,
        '1-10km': 0,
        '10-50km': 0,
        '50-200km': 0,
        '200-1000km': 0,
        '1000km+': 0
    }

    for d in distances:
        if d <= 100:
            distance_buckets['0-100m'] += 1
        elif d <= 1000:
            distance_buckets['100m-1km'] += 1
        elif d <= 10000:
            distance_buckets['1-10km'] += 1
        elif d <= 50000:
            distance_buckets['10-50km'] += 1
        elif d <= 200000:
            distance_buckets['50-200km'] += 1
        elif d <= 1000000:
            distance_buckets['200-1000km'] += 1
        else:
            distance_buckets['1000km+'] += 1

    # Calculate statistics
    sorted_distances = sorted(distances)
    n = len(sorted_distances)
    avg_distance = sum(distances) / n if n > 0 else 0
    median_distance = sorted_distances[n // 2] if n > 0 else 0
    p95_distance = sorted_distances[int(n * 0.95)] if n > 0 else 0

    distance_distribution = {
        'buckets': distance_buckets,
        'stats': {
            'count': n,
            'avg_km': avg_distance / 1000,
            'median_km': median_distance / 1000,
            'p95_km': p95_distance / 1000
        }
    }

    # 4. Region stats - reverse geocode actual locations to get regions
    region_stats = {}

    # Filter rounds with valid coordinates
    valid_rounds = [r for r in rounds_data
                    if r['actualLat'] is not None and r['actualLng'] is not None]
    actual_coords = [(r['actualLat'], r['actualLng']) for r in valid_rounds]

    # Also get guess coordinates for hit rate calculation
    guess_coords_for_regions = [(r.get('guessLat'), r.get('guessLng')) for r in valid_rounds]

    if actual_coords:
        try:
            geo_results = rg.search(actual_coords)

            # Batch geocode guess coordinates for hit rate (region-level)
            guess_regions = []
            valid_guess_coords = [(lat, lng) for lat, lng in guess_coords_for_regions
                                  if lat is not None and lng is not None]
            if valid_guess_coords:
                guess_geo_results = rg.search(valid_guess_coords)
                guess_idx = 0
                for lat, lng in guess_coords_for_regions:
                    if lat is not None and lng is not None:
                        guess_regions.append({
                            'country': guess_geo_results[guess_idx]['cc'].lower(),
                            'region': guess_geo_results[guess_idx].get('admin1', '') or ''
                        })
                        guess_idx += 1
                    else:
                        guess_regions.append(None)
            else:
                guess_regions = [None] * len(valid_rounds)

            for i, result in enumerate(geo_results):
                # Skip regions that don't belong to the requested country
                geocoded_country = result.get('cc', '').lower()
                if geocoded_country != country_code:
                    continue

                region = result.get('admin1', '') or ''
                # Skip locations where we can't determine the region
                if not region.strip():
                    continue

                if region not in region_stats:
                    region_stats[region] = {
                        'rounds': 0,
                        'total_score': 0,
                        'total_distance': 0,
                        'score_diffs': [],
                        'wins': 0,
                        'correct_guesses': 0,
                        'total_guesses': 0
                    }

                rd = valid_rounds[i]
                stats = region_stats[region]
                stats['rounds'] += 1
                stats['total_score'] += rd['score']
                stats['total_distance'] += rd['distance']

                # Score diff and win rate
                enemy_score = rd.get('enemyScore', 0)
                score_diff = rd['score'] - enemy_score
                stats['score_diffs'].append(score_diff)
                if score_diff > 0:
                    stats['wins'] += 1

                # Hit rate - did we guess the correct region?
                guess_info = guess_regions[i]
                if guess_info is not None:
                    stats['total_guesses'] += 1
                    # Check if guessed region matches actual region
                    if (guess_info['country'] == country_code and
                            guess_info['region'] == region):
                        stats['correct_guesses'] += 1

        except Exception as e:
            print(f"Reverse geocoding error for regions: {e}")

    # Calculate metrics per region
    region_list = []
    for region, stats in region_stats.items():
        rounds_count = stats['rounds']
        avg_score = stats['total_score'] / rounds_count if rounds_count > 0 else 0
        avg_distance = stats['total_distance'] / rounds_count if rounds_count > 0 else 0
        avg_score_diff = sum(stats['score_diffs']) / len(stats['score_diffs']) if stats['score_diffs'] else 0
        win_rate = stats['wins'] / rounds_count if rounds_count > 0 else 0
        hit_rate = stats['correct_guesses'] / stats['total_guesses'] if stats['total_guesses'] > 0 else 0

        region_list.append({
            'region': region,
            'rounds': rounds_count,
            'avg_score': avg_score,
            'avg_distance_km': avg_distance / 1000,
            'avg_score_diff': avg_score_diff,
            'win_rate': win_rate,
            'hit_rate': hit_rate
        })

    # Sort by score_diff descending (best first)
    region_list.sort(key=lambda x: x['avg_score_diff'], reverse=True)

    return flask.jsonify({
        "success": True,
        "data": {
            "country_code": country_code,
            "total_rounds": len(rounds_data),
            "heatmap_data": heatmap_data,
            "wrong_guesses": wrong_guesses_list,
            "distance_distribution": distance_distribution,
            "region_stats": region_list
        }
    })


@geodash.app.route('/api/v1/fetch-all/', methods=['POST'])
def fetch_all():
    """Fetch all games (both duels and team duels) and compute all stat variations."""
    data = flask.request.get_json()

    if not data or 'playerId' not in data:
        return flask.jsonify({"success": False, "error": "playerId is required"}), 400
    if 'ncfa' not in data:
        return flask.jsonify({"success": False, "error": "ncfa is required"}), 400

    player_id = data['playerId']
    ncfa = data['ncfa']

    try:
        # Create authenticated session
        session = requests.Session()
        session.cookies.set("_ncfa", ncfa, domain="www.geoguessr.com")
        session.cookies.set("_ncfa", ncfa, domain="game-server.geoguessr.com")

        db = get_db()
        results = {
            "duels": {"new": 0, "total": 0},
            "team_duels": {"new": 0, "total": 0}
        }

        # --- Fetch Solo Duels ---
        duels_game_ids = fetch_filtered_tokens(session, game_type="duels", mode_filter="all")

        if duels_game_ids:
            cur = db.execute(
                "SELECT game_id FROM fetched_games WHERE player_id = ? AND game_type = ?",
                (player_id, 'duels')
            )
            existing_ids = {row['game_id'] for row in cur.fetchall()}
            new_duels_ids = {
                gid: mode for gid, mode in duels_game_ids.items()
                if gid not in existing_ids
            }

            if new_duels_ids:
                new_duels = fetch_duels(session, new_duels_ids, player_id)

                for gid in new_duels_ids.keys():
                    db.execute(
                        "INSERT OR IGNORE INTO fetched_games (game_id, player_id, game_type) VALUES (?, ?, ?)",
                        (gid, player_id, 'duels')
                    )
                results["duels"]["new"] = len(new_duels)
            else:
                new_duels = []

            try:
                existing_duels = load_json("data/games.json")
            except Exception:
                existing_duels = []

            all_duels = existing_duels + new_duels
            save_json("data/games.json", all_duels)
            results["duels"]["total"] = len(all_duels)

        # --- Fetch Team Duels ---
        team_game_ids = fetch_filtered_tokens(session, game_type="team", mode_filter="all")

        if team_game_ids:
            cur = db.execute(
                "SELECT game_id FROM fetched_games WHERE player_id = ? AND game_type = ?",
                (player_id, 'team_duels')
            )
            existing_ids = {row['game_id'] for row in cur.fetchall()}
            new_team_ids = {
                gid: mode for gid, mode in team_game_ids.items()
                if gid not in existing_ids
            }

            if new_team_ids:
                new_team = fetch_team_duels(session, new_team_ids, player_id)

                for gid in new_team_ids.keys():
                    db.execute(
                        "INSERT OR IGNORE INTO fetched_games (game_id, player_id, game_type) VALUES (?, ?, ?)",
                        (gid, player_id, 'team_duels')
                    )
                results["team_duels"]["new"] = len(new_team)
            else:
                new_team = []

            try:
                existing_team = load_json("data/team_games.json")
            except Exception:
                existing_team = []

            all_team = existing_team + new_team
            save_json("data/team_games.json", all_team)
            results["team_duels"]["total"] = len(all_team)

        # --- Fetch usernames for all players in team games ---
        try:
            all_team = load_json("data/team_games.json")
            player_ids = set()
            for game in all_team:
                player_ids.update(game.get('playerStats', {}).keys())

            print(f"Fetching usernames for {len(player_ids)} players...")
            for pid in player_ids:
                _fetch_username(session, pid)
        except Exception as e:
            print(f"Error fetching usernames: {e}")

        # --- Compute and store all stat variations ---
        _compute_and_store_all_variations(player_id)

        return flask.jsonify({
            "success": True,
            "duels_fetched": results["duels"]["new"],
            "duels_total": results["duels"]["total"],
            "team_duels_fetched": results["team_duels"]["new"],
            "team_duels_total": results["team_duels"]["total"]
        })

    except Exception as e:
        return flask.jsonify({"success": False, "error": str(e)}), 500


def _sse_event(event_type, data):
    """Format a Server-Sent Event message."""
    import json
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@geodash.app.route('/api/v1/fetch-all-stream/', methods=['GET'])
def fetch_all_stream():
    """Fetch all games with SSE progress updates."""
    player_id = flask.request.args.get('playerId')
    ncfa = flask.request.args.get('ncfa')

    if not player_id:
        return flask.jsonify({"success": False, "error": "playerId is required"}), 400
    if not ncfa:
        return flask.jsonify({"success": False, "error": "ncfa is required"}), 400

    def generate():
        try:
            # Create authenticated session
            session = requests.Session()
            session.cookies.set("_ncfa", ncfa, domain="www.geoguessr.com")
            session.cookies.set("_ncfa", ncfa, domain="game-server.geoguessr.com")

            with geodash.app.app_context():
                db = get_db()
                results = {
                    "duels": {"new": 0, "total": 0},
                    "team_duels": {"new": 0, "total": 0}
                }

                # --- Phase 1: Fetch Duel Tokens ---
                yield _sse_event("phase", {"phase": 1, "name": "Fetching Duel tokens", "status": "in_progress"})

                duels_game_ids = fetch_filtered_tokens(session, game_type="duels", mode_filter="all")
                yield _sse_event("phase", {
                    "phase": 1,
                    "name": "Fetching Duel tokens",
                    "status": "complete",
                    "count": len(duels_game_ids)
                })

                # --- Phase 2: Fetch Duel Games ---
                if duels_game_ids:
                    cur = db.execute(
                        "SELECT game_id FROM fetched_games WHERE player_id = ? AND game_type = ?",
                        (player_id, 'duels')
                    )
                    existing_ids = {row['game_id'] for row in cur.fetchall()}
                    new_duels_ids = {
                        gid: mode for gid, mode in duels_game_ids.items()
                        if gid not in existing_ids
                    }

                    total_new = len(new_duels_ids)
                    yield _sse_event("phase", {
                        "phase": 2,
                        "name": "Fetching Duel games",
                        "status": "in_progress",
                        "total": total_new,
                        "current": 0
                    })

                    new_duels = []
                    if new_duels_ids:
                        game_ids_list = list(new_duels_ids.keys())
                        for i, gid in enumerate(game_ids_list, 1):
                            is_competitive = new_duels_ids.get(gid, False)
                            result = fetch_single_duel(session, gid, player_id, is_competitive)
                            if result:
                                new_duels.append(result)

                            db.execute(
                                "INSERT OR IGNORE INTO fetched_games (game_id, player_id, game_type) VALUES (?, ?, ?)",
                                (gid, player_id, 'duels')
                            )

                            # Yield progress every game
                            yield _sse_event("progress", {
                                "phase": 2,
                                "current": i,
                                "total": total_new
                            })

                            time.sleep(0.075)

                        results["duels"]["new"] = len(new_duels)

                    try:
                        existing_duels = load_json("data/games.json")
                    except Exception:
                        existing_duels = []

                    all_duels = existing_duels + new_duels
                    save_json("data/games.json", all_duels)
                    results["duels"]["total"] = len(all_duels)

                yield _sse_event("phase", {
                    "phase": 2,
                    "name": "Fetching Duel games",
                    "status": "complete",
                    "new": results["duels"]["new"],
                    "total": results["duels"]["total"]
                })

                # --- Phase 3: Fetch Team Duel Tokens ---
                yield _sse_event("phase", {"phase": 3, "name": "Fetching Team Duel tokens", "status": "in_progress"})

                team_game_ids = fetch_filtered_tokens(session, game_type="team", mode_filter="all")
                yield _sse_event("phase", {
                    "phase": 3,
                    "name": "Fetching Team Duel tokens",
                    "status": "complete",
                    "count": len(team_game_ids)
                })

                # --- Phase 4: Fetch Team Duel Games ---
                if team_game_ids:
                    cur = db.execute(
                        "SELECT game_id FROM fetched_games WHERE player_id = ? AND game_type = ?",
                        (player_id, 'team_duels')
                    )
                    existing_ids = {row['game_id'] for row in cur.fetchall()}
                    new_team_ids = {
                        gid: mode for gid, mode in team_game_ids.items()
                        if gid not in existing_ids
                    }

                    total_new = len(new_team_ids)
                    yield _sse_event("phase", {
                        "phase": 4,
                        "name": "Fetching Team Duel games",
                        "status": "in_progress",
                        "total": total_new,
                        "current": 0
                    })

                    new_team = []
                    if new_team_ids:
                        game_ids_list = list(new_team_ids.keys())
                        for i, gid in enumerate(game_ids_list, 1):
                            is_competitive = new_team_ids.get(gid, False)
                            result = fetch_single_team_duel(session, gid, player_id, is_competitive)
                            if result:
                                new_team.append(result)

                            db.execute(
                                "INSERT OR IGNORE INTO fetched_games (game_id, player_id, game_type) VALUES (?, ?, ?)",
                                (gid, player_id, 'team_duels')
                            )

                            # Yield progress every game
                            yield _sse_event("progress", {
                                "phase": 4,
                                "current": i,
                                "total": total_new
                            })

                            time.sleep(0.075)

                        results["team_duels"]["new"] = len(new_team)

                    try:
                        existing_team = load_json("data/team_games.json")
                    except Exception:
                        existing_team = []

                    all_team = existing_team + new_team
                    save_json("data/team_games.json", all_team)
                    results["team_duels"]["total"] = len(all_team)

                yield _sse_event("phase", {
                    "phase": 4,
                    "name": "Fetching Team Duel games",
                    "status": "complete",
                    "new": results["team_duels"]["new"],
                    "total": results["team_duels"]["total"]
                })

                # --- Phase 5: Fetch usernames ---
                yield _sse_event("phase", {"phase": 5, "name": "Fetching player usernames", "status": "in_progress"})
                try:
                    all_team = load_json("data/team_games.json")
                    player_ids = set()
                    for game in all_team:
                        player_ids.update(game.get('playerStats', {}).keys())

                    for pid in player_ids:
                        _fetch_username(session, pid)
                except Exception as e:
                    print(f"Error fetching usernames: {e}")

                yield _sse_event("phase", {"phase": 5, "name": "Fetching player usernames", "status": "complete"})

                # --- Phase 6: Compute statistics ---
                yield _sse_event("phase", {"phase": 6, "name": "Computing statistics", "status": "in_progress"})
                _compute_and_store_all_variations(player_id)
                yield _sse_event("phase", {"phase": 6, "name": "Computing statistics", "status": "complete"})

                # --- Done ---
                yield _sse_event("complete", {
                    "success": True,
                    "duels_fetched": results["duels"]["new"],
                    "duels_total": results["duels"]["total"],
                    "team_duels_fetched": results["team_duels"]["new"],
                    "team_duels_total": results["team_duels"]["total"]
                })

        except InvalidPlayerIdError as e:
            yield _sse_event("error", {
                "error": "This player ID doesn't match your account. Check that you copied it correctly.",
                "field": "playerId"
            })
        except AuthenticationError as e:
            error_msg = str(e)
            # Provide user-friendly messages based on the error
            if "401" in error_msg or "403" in error_msg or "Invalid _ncfa" in error_msg:
                yield _sse_event("error", {
                    "error": "Invalid or expired NCFA token. Try copying a fresh token from your browser.",
                    "field": "ncfa"
                })
            else:
                yield _sse_event("error", {
                    "error": "Authentication failed. Please check your credentials and try again.",
                    "field": "ncfa"
                })
        except requests.exceptions.ConnectionError:
            yield _sse_event("error", {
                "error": "Connection to the GeoGuessr API failed. Please check your internet connection and try again."
            })
        except requests.exceptions.Timeout:
            yield _sse_event("error", {
                "error": "Request timed out. The GeoGuessr API may be slow. Please try again."
            })
        except Exception as e:
            yield _sse_event("error", {
                "error": "Something went wrong while fetching your games. Please try again. If this keeps happening, the GeoGuessr API may be temporarily unavailable."
            })

    return flask.Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


def _compute_and_store_all_variations(player_id):
    """Compute and store stats for all 6 filter combinations."""
    try:
        all_duels = load_json("data/games.json")
    except Exception:
        all_duels = []

    try:
        all_team = load_json("data/team_games.json")
    except Exception:
        all_team = []

    # Duels variations
    if all_duels:
        stats = process_duels(all_duels)
        _save_stats_to_db(player_id, 'duels', 'duels_all', stats)

        competitive = [g for g in all_duels if g.get('isCompetitive', False)]
        if competitive:
            stats = process_duels(competitive)
            _save_stats_to_db(player_id, 'duels', 'duels_competitive', stats)

        casual = [g for g in all_duels if not g.get('isCompetitive', False)]
        if casual:
            stats = process_duels(casual)
            _save_stats_to_db(player_id, 'duels', 'duels_casual', stats)

    # Team duels variations
    if all_team:
        stats = process_games(all_team)
        _save_stats_to_db(player_id, 'team_duels', 'team_duels_all', stats)

        competitive = [g for g in all_team if g.get('isCompetitive', False)]
        if competitive:
            stats = process_games(competitive)
            _save_stats_to_db(player_id, 'team_duels', 'team_duels_competitive', stats)

        casual = [g for g in all_team if not g.get('isCompetitive', False)]
        if casual:
            stats = process_games(casual)
            _save_stats_to_db(player_id, 'team_duels', 'team_duels_casual', stats)


def _save_stats_to_db(player_id, game_type, filter_type, stats):
    """Save processed stats to the database."""
    db = get_db()

    overall = stats['overall']

    if game_type == 'duels':
        cur = db.execute(
            """INSERT INTO overall_stats
               (player_id, game_type, filter_type, total_games, win_percentage, avg_rounds_per_game,
                avg_score, total_5ks, avg_guess_time, multi_merchant, reverse_merchant)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (player_id, game_type, filter_type, overall['total_games'], overall['win_percentage'],
             overall['avg_rounds_per_game'], overall.get('avg_score'),
             overall.get('total_5ks'), overall.get('avg_guess_time'),
             overall['merchant_stats']['multi_merchant'],
             overall['merchant_stats']['reverse_merchant'])
        )
    else:
        cur = db.execute(
            """INSERT INTO overall_stats
               (player_id, game_type, filter_type, total_games, win_percentage, avg_rounds_per_game,
                multi_merchant, reverse_merchant)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (player_id, game_type, filter_type, overall['total_games'], overall['win_percentage'],
             overall['avg_rounds_per_game'],
             overall['merchant_stats']['multi_merchant'],
             overall['merchant_stats']['reverse_merchant'])
        )

    overall_id = cur.lastrowid

    # Insert player contributions (for team duels)
    if game_type == 'team_duels':
        games_per_player = overall.get('games_per_player', {})
        for pid, contrib in overall.get('player_contribution_percent', {}).items():
            db.execute(
                """INSERT INTO player_contributions
                   (overall_stats_id, player_id, contribution_percent, avg_individual_score,
                    total_5ks, avg_guess_time, games_played)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (overall_id, pid, contrib,
                 overall.get('avg_individual_score', {}).get(pid),
                 overall.get('player_total_5ks', {}).get(pid),
                 overall.get('avg_guess_time', {}).get(pid),
                 games_per_player.get(pid, 0))
            )

    # Insert country stats
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
