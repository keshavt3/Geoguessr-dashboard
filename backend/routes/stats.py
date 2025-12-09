from flask import Blueprint, jsonify, request
from backend.services.stats_service import get_stats, fetch_and_process

stats_bp = Blueprint('stats', __name__)

@stats_bp.route('/api/stats')
def stats():
    return jsonify({"success": True, "data": get_stats()})

@stats_bp.route('/api/fetch-latest', methods=['POST'])
def fetch_latest():
    data = request.get_json()
    if not data or 'playerId' not in data:
        return jsonify({"success": False, "error": "playerId is required"}), 400
    if 'ncfa' not in data:
        return jsonify({"success": False, "error": "ncfa is required"}), 400
    try:
        fetch_and_process(data['playerId'], data['ncfa'])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
