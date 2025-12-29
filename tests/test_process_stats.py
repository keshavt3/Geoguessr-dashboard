"""Tests for geoguessr.process_stats module."""
import pytest
from unittest.mock import patch

from geoguessr.process_stats import process_games, process_duels


def make_team_game(
    player1_id="player1",
    player2_id="player2",
    rounds_data=None,
    health_change=-3000,
    score_diff=500,
):
    """Create a mock team game for testing."""
    if rounds_data is None:
        rounds_data = [
            {
                "roundNumber": 1,
                "p1": {"score": 4500, "distance": 100, "lat": 48.8, "lng": 2.3, "time": 15.0},
                "p2": {"score": 4000, "distance": 200, "lat": 48.7, "lng": 2.2, "time": 18.0},
                "country": "fr",
                "enemyBestScore": 4200,
            },
        ]

    p1_rounds = []
    p2_rounds = []
    round_stats = []

    for rd in rounds_data:
        rn = rd["roundNumber"]
        p1 = rd["p1"]
        p2 = rd["p2"]

        p1_rounds.append({
            "roundNumber": rn,
            "score": p1["score"],
            "distance": p1["distance"],
            "country": rd["country"],
            "lat": p1["lat"],
            "lng": p1["lng"],
            "time": p1.get("time"),
        })
        p2_rounds.append({
            "roundNumber": rn,
            "score": p2["score"],
            "distance": p2["distance"],
            "country": rd["country"],
            "lat": p2["lat"],
            "lng": p2["lng"],
            "time": p2.get("time"),
        })
        round_stats.append({
            "roundNumber": rn,
            "enemyBestScore": rd["enemyBestScore"],
        })

    return {
        "gameId": "test-game-id",
        "playerStats": {
            player1_id: {"rounds": p1_rounds},
            player2_id: {"rounds": p2_rounds},
        },
        "teamStats": {
            "totalHealthChange": health_change,
            "scoreDiff": score_diff,
        },
        "roundStats": round_stats,
    }


def make_duel_game(rounds_data=None, total_score=4500):
    """Create a mock solo duel game for testing."""
    if rounds_data is None:
        rounds_data = [
            {
                "roundNumber": 1,
                "score": 4500,
                "distance": 100,
                "lat": 48.8,
                "lng": 2.3,
                "time": 15.0,
                "country": "fr",
                "enemyScore": 4000,
                "totalHealthChange": 500,
            },
        ]

    player_rounds = []
    round_stats = []

    for rd in rounds_data:
        player_rounds.append({
            "roundNumber": rd["roundNumber"],
            "score": rd["score"],
            "distance": rd["distance"],
            "country": rd["country"],
            "lat": rd["lat"],
            "lng": rd["lng"],
            "time": rd.get("time"),
        })
        round_stats.append({
            "roundNumber": rd["roundNumber"],
            "enemyScore": rd["enemyScore"],
            "totalHealthChange": rd["totalHealthChange"],
            "country": rd["country"],
        })

    return {
        "gameId": "test-duel-id",
        "playerStats": {
            "totalScore": total_score,
            "rounds": player_rounds,
        },
        "roundStats": round_stats,
    }


class TestProcessGames:
    """Tests for process_games function (team duels)."""

    @patch("geoguessr.process_stats.rg.search")
    def test_empty_games_list(self, mock_rg):
        mock_rg.return_value = []
        result = process_games([])

        assert result["overall"]["total_games"] == 0
        assert result["overall"]["win_percentage"] == 0

    @patch("geoguessr.process_stats.rg.search")
    def test_single_game_win(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        games = [make_team_game(health_change=-3000)]  # Won (didn't lose all health)

        result = process_games(games)

        assert result["overall"]["total_games"] == 1
        assert result["overall"]["win_percentage"] == 1.0

    @patch("geoguessr.process_stats.rg.search")
    def test_single_game_loss(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        games = [make_team_game(health_change=-6000)]  # Lost (all health gone)

        result = process_games(games)

        assert result["overall"]["total_games"] == 1
        assert result["overall"]["win_percentage"] == 0.0

    @patch("geoguessr.process_stats.rg.search")
    def test_player_contribution_tracked(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        # Player 1 has better distance (100 < 200), so should get contribution
        games = [make_team_game()]

        result = process_games(games)

        contrib = result["overall"]["player_contribution_percent"]
        assert "player1" in contrib
        assert contrib["player1"] == 1.0  # Won the only round
        # player2 is not in contrib dict because they never contributed

    @patch("geoguessr.process_stats.rg.search")
    def test_merchant_stats_multi_merchant(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        # Lost game but outscored opponent
        games = [make_team_game(health_change=-6000, score_diff=500)]

        result = process_games(games)

        assert result["overall"]["merchant_stats"]["multi_merchant"] == 1

    @patch("geoguessr.process_stats.rg.search")
    def test_merchant_stats_reverse_merchant(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        # Won game but got outscored
        games = [make_team_game(health_change=-3000, score_diff=-500)]

        result = process_games(games)

        assert result["overall"]["merchant_stats"]["reverse_merchant"] == 1

    @patch("geoguessr.process_stats.rg.search")
    def test_skips_non_2player_games(self, mock_rg):
        mock_rg.return_value = []
        # Create game with 3 players (invalid)
        game = make_team_game()
        game["playerStats"]["player3"] = {"rounds": []}

        result = process_games([game])

        assert result["overall"]["total_games"] == 0

    @patch("geoguessr.process_stats.rg.search")
    def test_country_stats_collected(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        games = [make_team_game()]

        result = process_games(games)

        # Countries should be a list of tuples after sorting
        assert isinstance(result["countries"], list)
        assert len(result["countries"]) == 1
        country_code, stats = result["countries"][0]
        assert country_code == "fr"
        assert stats["rounds"] == 1


class TestProcessDuels:
    """Tests for process_duels function (solo duels)."""

    @patch("geoguessr.process_stats.rg.search")
    def test_empty_games_list(self, mock_rg):
        mock_rg.return_value = []
        result = process_duels([])

        assert result["overall"]["total_games"] == 0
        assert result["overall"]["win_percentage"] == 0

    @patch("geoguessr.process_stats.rg.search")
    def test_single_game_win(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        # Total health change > -6000 means win
        games = [make_duel_game()]

        result = process_duels(games)

        assert result["overall"]["total_games"] == 1
        assert result["overall"]["win_percentage"] == 1.0

    @patch("geoguessr.process_stats.rg.search")
    def test_avg_score_calculated(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        games = [make_duel_game()]

        result = process_duels(games)

        assert result["overall"]["avg_score"] == 4500

    @patch("geoguessr.process_stats.rg.search")
    def test_5k_count(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        rounds = [
            {
                "roundNumber": 1,
                "score": 5000,
                "distance": 0,
                "lat": 48.8,
                "lng": 2.3,
                "time": 10.0,
                "country": "fr",
                "enemyScore": 4000,
                "totalHealthChange": 1000,
            },
        ]
        games = [make_duel_game(rounds_data=rounds, total_score=5000)]

        result = process_duels(games)

        assert result["overall"]["total_5ks"] == 1

    @patch("geoguessr.process_stats.rg.search")
    def test_country_win_rate(self, mock_rg):
        mock_rg.return_value = [{"cc": "FR"}]
        # Player scores 4500, enemy scores 4000 -> round win
        games = [make_duel_game()]

        result = process_duels(games)

        country_code, stats = result["countries"][0]
        assert stats["win_rate"] == 1.0
