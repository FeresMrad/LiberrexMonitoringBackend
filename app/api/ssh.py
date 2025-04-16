"""SSH-related API endpoints."""
import re
import json
from collections import Counter
from flask import Blueprint, jsonify, request
from app.services.victorialogs import query_victorialogs
from app.services.influxdb import query_influxdb
from .utils import parse_time_parameters

# Create a blueprint for SSH endpoints
ssh_bp = Blueprint('ssh', __name__, url_prefix='/ssh')

@ssh_bp.route('/failed', methods=['GET'])
def get_ssh_failed():
    """Get count of failed SSH login attempts for a host."""
    host = request.args.get('host')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    start, end = parse_time_parameters(request)
    query = f'hostname:{host} app_name:sshd Failed password'
    logs = query_victorialogs(query, start, end)

    return jsonify({"count": len(logs)})


@ssh_bp.route('/failed/unique', methods=['GET'])
def get_ssh_failed_unique():
    """Get count of unique IPs that attempted failed SSH logins."""
    host = request.args.get('host')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    start, end = parse_time_parameters(request)
    query = f'hostname:{host} app_name:sshd Failed password'
    logs = query_victorialogs(query, start, end)

    # Extract IP addresses using regex
    ip_set = set()
    ip_regex = re.compile(r'from\s+(\d+\.\d+\.\d+\.\d+)', re.IGNORECASE)

    for log in logs:
        message = log.get('_msg', '')
        match = ip_regex.search(message)
        if match:
            ip_set.add(match.group(1))

    return jsonify({"count": len(ip_set)})


@ssh_bp.route('/failed/ips', methods=['GET'])
def get_ssh_failed_ips():
    """Get details of IPs that attempted failed SSH logins."""
    host = request.args.get('host')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    start, end = parse_time_parameters(request)
    query = f'hostname:{host} app_name:sshd Failed password'
    logs = query_victorialogs(query, start, end)

    # Count occurrences of each IP
    ip_counts = Counter()
    ip_regex = re.compile(r'from\s+(\d+\.\d+\.\d+\.\d+)', re.IGNORECASE)

    for log in logs:
        message = log.get('_msg', '')
        match = ip_regex.search(message)
        if match:
            ip_counts[match.group(1)] += 1

    # Convert to list of [ip, count] entries, sorted by count
    ip_list = [[ip, count] for ip, count in ip_counts.most_common()]

    return jsonify(ip_list)


@ssh_bp.route('/failed/users', methods=['GET'])
def get_ssh_failed_users():
    """Get details of usernames that were targeted in failed SSH logins."""
    host = request.args.get('host')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    start, end = parse_time_parameters(request)
    query = f'hostname:{host} app_name:sshd Failed password'
    logs = query_victorialogs(query, start, end)

    # Count occurrences of each username
    user_counts = Counter()
    user_regex = re.compile(r'Failed password for (?:invalid user )?(\S+)\s+from', re.IGNORECASE)

    for log in logs:
        message = log.get('_msg', '')
        match = user_regex.search(message)
        if match:
            user_counts[match.group(1)] += 1

    # Calculate total attempts
    total_attempts = sum(user_counts.values())

    # Generate a unique color for each user
    users = list(user_counts.keys())
    user_colors = {}

    for i, user in enumerate(users):
        hue = (i * 360 / len(users)) if users else 0
        user_colors[user] = f"hsl({hue}, 90%, 70%)"

    result = {
        "counts": dict(user_counts),
        "colors": user_colors,
        "total": total_attempts
    }

    return jsonify(result)


@ssh_bp.route('/logs', methods=['GET'])
def get_ssh_logs():
    """Get SSH logs for a specific host."""
    host = request.args.get('host')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    # Parse time range parameters
    start, end = parse_time_parameters(request)

    # If no time parameters were specified, default to last 60 minutes
    if not start and not end:
        start = '60m'

    # Build and execute the query with the provided time range
    query = f'hostname:{host} app_name:sshd'
    logs = query_victorialogs(query, start, end)

    return jsonify(logs)


@ssh_bp.route('/sessions', methods=['GET'])
def get_ssh_sessions():
    """Get active SSH sessions for a host."""
    host = request.args.get('host')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    query = f'SELECT "active_count", "sessions_json" FROM "ssh_sessions" WHERE "host" = \'{host}\' ORDER BY time DESC LIMIT 1'
    response = query_influxdb(query)

    result = {
        "active_count": 0,
        "sessions": []
    }

    if response["results"][0].get("series"):
        values = response["results"][0]["series"][0]["values"][0]
        active_count = values[1]
        sessions_json = values[2]

        result = {
            "active_count": active_count,
            "sessions": json.loads(sessions_json) if sessions_json else []
        }

    return jsonify(result)


@ssh_bp.route('/accepted/users', methods=['GET'])
def get_ssh_accepted_users():
    """Get details of usernames for accepted SSH logins."""
    host = request.args.get('host')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    start, end = parse_time_parameters(request)
    query = f'hostname:{host} app_name:sshd "Accepted password"'
    logs = query_victorialogs(query, start, end)

    # Count occurrences of each username
    user_counts = Counter()
    user_regex = re.compile(r'Accepted password for (\S+)\s+from', re.IGNORECASE)

    for log in logs:
        message = log.get('_msg', '')
        match = user_regex.search(message)
        if match:
            user_counts[match.group(1)] += 1

    # Calculate total attempts
    total_attempts = sum(user_counts.values())

    result = {
        "counts": dict(user_counts),
        "total": total_attempts
    }

    return jsonify(result)
