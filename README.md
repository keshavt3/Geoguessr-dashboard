# GeoGuessr Statistics Dashboard

A statistics dashboard that fetches game data from the GeoGuessr API and processes it into detailed player and team statistics. Supports both Team Duels (2v2) and solo Duels (1v1) game modes.

## Features

- Fetch game history from GeoGuessr API
- Support for Team Duels (2v2) and solo Duels (1v1)
- Filter by competitive or casual games
- Per-country performance analytics with score differentials
- Player contribution rates and teammate comparisons
- Interactive world map visualization
- Web dashboard with real-time fetch progress

## Requirements

- Python 3.10+
- GeoGuessr account with `_ncfa` authentication cookie

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/geoguessr-dashboard.git
cd geoguessr-dashboard

# Create and activate virtual environment
python -m venv myenv
source myenv/bin/activate

# Install dependencies
pip install -e .

# For development (includes pytest, linting tools)
pip install -e ".[dev]"
```

## Usage

### Web Dashboard

```bash
# Initialize the database (first time only)
bin/geodashdb create

# Start the development server
bin/geodashrun

# Open http://localhost:8000 in your browser
```

### CLI Data Fetching

```bash
# Interactive CLI for fetching and processing game data
python main.py

# Or run individual scripts
python geoguessr/fetch_games.py   # Fetch games only
python geoguessr/process_stats.py # Process existing games.json
```

### Database Commands

```bash
bin/geodashdb create  # Initialize database
bin/geodashdb reset   # Reset database and delete game data
bin/geodashdb dump    # View database contents
```

## Authentication

This dashboard requires your GeoGuessr `_ncfa` cookie for API access:

1. Log into GeoGuessr in your browser
2. Open Developer Tools (F12) > Application > Cookies
3. Copy the value of the `_ncfa` cookie
4. Enter it when prompted by the CLI or web dashboard

## Statistics Computed

**Overall Statistics:**
- Win percentage and average rounds per game
- Player contribution rates
- Average scores and 5k counts
- Guess times
- Merchant stats (lost but outscored / won but outscored)

**Per-Country Statistics:**
- Average scores and distances
- 5k rates (perfect score percentage)
- Hit rates (correct country guesses)
- Win rates and score differentials
- Top/bottom 10 countries ranked by score differential (minimum 20 rounds)

## Project Structure

```
geoguessr-dashboard/
├── geoguessr/           # Data pipeline
│   ├── fetch_games.py   # API fetching logic
│   ├── process_stats.py # Statistics aggregation
│   └── utils.py         # Shared utilities
├── geodash/             # Flask web dashboard
│   ├── api/             # REST API endpoints
│   ├── views/           # Page routes
│   └── model.py         # Database layer
├── bin/                 # CLI scripts
├── sql/                 # Database schema
├── tests/               # Test suite
└── main.py              # CLI entry point
```

## Running Tests

```bash
pytest                     # Run all tests
pytest tests/test_file.py  # Run specific test file
pytest -v                  # Verbose output
```

## License

MIT