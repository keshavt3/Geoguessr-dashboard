import json
from datetime import datetime

def load_data(path):
    with open(path, "r") as f:
        return json.load(f)

def save_json(path: str, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    
def parse_time(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def calculate_score(distance, size=14916862):
    distance = max(distance, 0)
    return round(5000 * (2.71828 ** (-10 * distance / size)))