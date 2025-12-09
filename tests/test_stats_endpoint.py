import pytest
import json
import os
from unittest.mock import patch
from backend import create_app

DUMMY_GAMES = [
    {
        "teamStats": {
            "totalHealthChange": -3000,
            "scoreDiff": 500
        },
        "playerStats": {
            "player1": {
                "rounds": [
                    {"roundNumber": 1, "score": 4500, "distance": 100.0, "country": "US", "lat": 40.0, "lng": -74.0, "time": 15.0},
                    {"roundNumber": 2, "score": 5000, "distance": 0.0, "country": "FR", "lat": 48.8, "lng": 2.3, "time": 12.0}
                ]
            },
            "player2": {
                "rounds": [
                    {"roundNumber": 1, "score": 4000, "distance": 200.0, "country": "US", "lat": 41.0, "lng": -73.0, "time": 18.0},
                    {"roundNumber": 2, "score": 4800, "distance": 50.0, "country": "FR", "lat": 48.9, "lng": 2.4, "time": 14.0}
                ]
            }
        },
        "roundStats": [
            {"roundNumber": 1, "enemyBestScore": 4200},
            {"roundNumber": 2, "enemyBestScore": 4900}
        ]
    }
]

@pytest.fixture
def app(tmp_path):
    dummy_file = tmp_path / "games.json"
    dummy_file.write_text(json.dumps(DUMMY_GAMES))

    with patch('backend.services.stats_service.DATA_PATH', str(dummy_file)):
        app = create_app()
        app.config['TESTING'] = True
        yield app

@pytest.fixture
def client(app):
    return app.test_client()

def test_stats_endpoint_returns_200(client):
    response = client.get('/api/stats')
    assert response.status_code == 200

def test_stats_endpoint_returns_json(client):
    response = client.get('/api/stats')
    assert response.content_type == 'application/json'

def test_stats_contains_overall(client):
    response = client.get('/api/stats')
    data = response.get_json()
    assert 'overall' in data

def test_stats_overall_has_expected_fields(client):
    response = client.get('/api/stats')
    data = response.get_json()
    overall = data['overall']

    assert 'total_games' in overall
    assert 'win_percentage' in overall
    assert 'avg_rounds_per_game' in overall
    assert 'player_contribution_percent' in overall
    assert 'avg_individual_score' in overall
    assert 'merchant_stats' in overall

def test_stats_total_games_correct(client):
    response = client.get('/api/stats')
    data = response.get_json()
    assert data['overall']['total_games'] == 1

def test_stats_win_percentage_correct(client):
    response = client.get('/api/stats')
    data = response.get_json()
    # totalHealthChange is -3000 which is > -6000, so it's a win
    assert data['overall']['win_percentage'] == 1.0

def test_stats_contains_countries(client):
    response = client.get('/api/stats')
    data = response.get_json()
    assert 'countries' in data
