"""Logs-related API endpoints."""
from flask import Blueprint, jsonify, request
from app.services.victorialogs import query_victorialogs
from .utils import parse_time_parameters

# Create a blueprint for logs endpoints
logs_bp = Blueprint('logs', __name__, url_prefix='/logs')

@logs_bp.route('', methods=['GET'])
def get_logs():
    """Get logs for a specific host."""
    host = request.args.get('host')
    start = request.args.get('start')
    end = request.args.get('end')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    # Build the query
    query = f'hostname:{host}'

    # Default to last 5 minutes if no time range specified
    if not start and not end:
        start = '5m'

    logs = query_victorialogs(query, start, end)

    return jsonify(logs)
