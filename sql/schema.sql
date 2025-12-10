PRAGMA foreign_keys = ON;

-- Track which games have been fetched to avoid re-fetching
CREATE TABLE fetched_games(
    game_id VARCHAR(64) PRIMARY KEY,
    player_id VARCHAR(64) NOT NULL,
    game_type VARCHAR(20) NOT NULL,  -- 'duels' or 'team_duels'
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Overall stats for a fetch session
-- filter_type values: duels_all, duels_competitive, duels_casual, team_all, team_competitive, team_casual
CREATE TABLE overall_stats(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id VARCHAR(64) NOT NULL,
    game_type VARCHAR(20) NOT NULL,  -- 'duels' or 'team_duels'
    filter_type VARCHAR(30) NOT NULL,  -- e.g. 'duels_competitive', 'team_all'
    total_games INTEGER NOT NULL,
    win_percentage REAL NOT NULL,
    avg_rounds_per_game REAL NOT NULL,
    avg_score REAL,
    total_5ks INTEGER,
    avg_guess_time REAL,
    multi_merchant INTEGER NOT NULL DEFAULT 0,
    reverse_merchant INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Cache player ID to username mappings
CREATE TABLE player_names(
    player_id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(128) NOT NULL,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Player contribution stats (for team duels)
CREATE TABLE player_contributions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    overall_stats_id INTEGER NOT NULL,
    player_id VARCHAR(64) NOT NULL,
    contribution_percent REAL,
    avg_individual_score REAL,
    total_5ks INTEGER,
    avg_guess_time REAL,
    games_played INTEGER,  -- number of games played with this teammate
    FOREIGN KEY (overall_stats_id) REFERENCES overall_stats(id) ON DELETE CASCADE
);

-- Per-country statistics
CREATE TABLE country_stats(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    overall_stats_id INTEGER NOT NULL,
    country_code VARCHAR(5) NOT NULL,
    rounds INTEGER NOT NULL,
    avg_score REAL NOT NULL,
    avg_distance_km REAL NOT NULL,
    five_k_rate REAL NOT NULL,
    avg_score_diff REAL NOT NULL,
    hit_rate REAL NOT NULL,
    win_rate REAL NOT NULL,
    FOREIGN KEY (overall_stats_id) REFERENCES overall_stats(id) ON DELETE CASCADE
);
