"""InfluxDB webhook endpoint."""
import re
from flask import Blueprint, request, current_app

# Create a blueprint for the webhook
webhook_bp = Blueprint('webhook', __name__, url_prefix='/write')


@webhook_bp.route('', methods=['POST'])
def influxdb_webhook():
    """Receives data from InfluxDB and sends it to WebSocket clients."""
    try:
        from app import socketio, host_subscribers
        
        data = request.data.decode("utf-8").strip()
        if data:
            for line in data.split("\n"):
                # Extract measurement name, host, and timestamp
                match = re.match(r"(?P<measurement>\w+),host=(?P<host>[\w\-]+) (?P<fields>.+) (?P<timestamp>\d+)", line)
                if match:
                    measurement = match.group("measurement")
                    host = match.group("host")  # Extract host
                    fields_str = match.group("fields")
                    timestamp = match.group("timestamp")

                    # Parse key-value fields
                    fields = {}
                    for field in fields_str.split(","):
                        # Skip empty fields
                        if not field.strip():
                            continue

                        # Handle the case where there's no '=' in the field
                        if '=' not in field:
                            continue

                        key, value = field.split("=", 1)  # Split on first '=' only
                        # Convert numerical values if possible
                        if value.replace(".", "", 1).isdigit():
                            value = float(value) if "." in value else int(value)
                        fields[key] = value

                    # Create structured data to emit
                    data_to_emit = {
                        "measurement": measurement,
                        "host": host,
                        "fields": fields,
                        "time": timestamp
                    }

                    # Emit to connected clients who are subscribed to this host
                    if host in host_subscribers and host_subscribers[host]:
                        print(f"Emitting data to {len(host_subscribers[host])} clients subscribed to {host}")
                        socketio.emit("metric_update", data_to_emit, room=host)

        return "", 204  # InfluxDB expects no response content
    except Exception as e:
        current_app.logger.error(f"Error processing InfluxDB data: {e}")
        return "Error", 400
