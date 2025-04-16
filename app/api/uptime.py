"""Uptime-related API endpoints."""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from app.services.influxdb import query_influxdb

# Create a blueprint for uptime endpoints
uptime_bp = Blueprint('uptime', __name__, url_prefix='/uptime')

@uptime_bp.route('', methods=['GET'])
def get_uptime():
    """Get uptime information for a host."""
    host = request.args.get('host')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    query = f'SELECT "uptime_seconds" FROM "uptime" WHERE "host" = \'{host}\' ORDER BY time DESC LIMIT 1'
    response = query_influxdb(query)

    result = {
        "isDown": True,
        "displayText": "Unknown",
        "lastUptimeTimestamp": None
    }

    if response["results"][0].get("series"):
        values = response["results"][0]["series"][0]["values"][0]
        timestamp_str = values[0]
        uptime_seconds = values[1]

        # Convert the timestamp to a timezone-aware datetime object
        last_timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # Make current_time timezone-aware (UTC)
        current_time = datetime.now(timezone.utc)

        diff_seconds = (current_time - last_timestamp).total_seconds()

        if diff_seconds > 60:
            result = {
                "isDown": True,
                "displayText": last_timestamp.strftime('%d/%m/%Y, %H:%M:%S'),
                "lastUptimeTimestamp": timestamp_str
            }
        else:
            current_uptime = uptime_seconds + diff_seconds

            # Format uptime
            days = int(current_uptime // 86400)
            hours = int((current_uptime % 86400) // 3600)
            minutes = int((current_uptime % 3600) // 60)
            seconds = int(current_uptime % 60)

            uptime_formatted = f"{days}d {hours}h {minutes}m {seconds}s"

            result = {
                "isDown": False,
                "displayText": uptime_formatted,
                "lastUptimeTimestamp": timestamp_str
            }

    return jsonify(result)
