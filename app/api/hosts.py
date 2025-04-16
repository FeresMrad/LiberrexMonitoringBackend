"""Host management API endpoints."""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app
from app.services.influxdb import query_influxdb, fetch_host_metric, write_to_influxdb

# Create a blueprint for host endpoints
hosts_bp = Blueprint('hosts', __name__, url_prefix='/hosts')

@hosts_bp.route('', methods=['GET'])
def get_hosts():
    """Get all monitored hosts with basic metrics."""
    query = 'SHOW TAG VALUES WITH KEY = "host"'
    response = query_influxdb(query)

    hosts_data = []

    # Fetch custom names in a separate query
    custom_names_query = 'SELECT last("custom_name") FROM "custom_data" GROUP BY "host"'
    custom_names_response = query_influxdb(custom_names_query)
    
    # Process custom names into a dictionary for easy lookup
    custom_names = {}
    if custom_names_response["results"][0].get("series"):
        for series in custom_names_response["results"][0]["series"]:
            if "tags" in series and "host" in series["tags"]:
                host_tag = series["tags"]["host"]
                custom_name = series["values"][0][1] if series["values"][0][1] is not None else ""
                custom_names[host_tag] = custom_name

    if response["results"][0].get("series"):
        for item in response["results"][0]["series"][0]["values"]:
            host_name = item[1]

            # Fetch host metrics
            host_data = {
                "name": host_name,
                "customName": custom_names.get(host_name, ""),  # Add custom name here
                "ip": fetch_host_metric(host_name, "network", "ip_adr"),
                "cpuUsage": fetch_host_metric(host_name, "cpu", "percent"),
                "memoryUsage": fetch_host_metric(host_name, "memory", "percent"),
                "diskUsage": fetch_host_metric(host_name, "disk", "percent"),
                "systemBoot": "Unknown"
            }

            # Fetch uptime
            uptime_query = f'SELECT "uptime_seconds" FROM "uptime" WHERE "host" = \'{host_name}\' ORDER BY time DESC LIMIT 1'
            uptime_response = query_influxdb(uptime_query)

            activity = {"isDown": True, "timestamp": "Unknown"}

            if uptime_response["results"][0].get("series"):
                values = uptime_response["results"][0]["series"][0]["values"][0]
                # Convert to timezone-aware datetime
                last_timestamp = datetime.fromisoformat(values[0].replace('Z', '+00:00'))
                uptime_seconds = values[1]

                # Make current_time timezone-aware (UTC)
                current_time = datetime.now(timezone.utc)

                time_diff = (current_time - last_timestamp).total_seconds()

                # Calculate system boot time
                boot_time = current_time.timestamp() - uptime_seconds
                host_data["systemBoot"] = datetime.fromtimestamp(boot_time).strftime('%d/%m/%Y, %H:%M:%S')

                activity = {
                    "isDown": time_diff > 61,
                    "timestamp": last_timestamp.strftime('%d/%m/%Y, %H:%M:%S') if time_diff > 61 else None
                }

            host_data["activity"] = activity
            hosts_data.append(host_data)

    return jsonify(hosts_data)

@hosts_bp.route('/name', methods=['POST'])
def update_host_name():
    """Update the custom name for a host."""
    data = request.get_json()
    host_id = data.get('hostId')
    custom_name = data.get('customName', '')
    
    if not host_id:
        return jsonify({"error": "Host ID is required"}), 400
    
    try:
        # Format the string value properly for line protocol
        # String values need to be enclosed in double quotes
        formatted_custom_name = f'"{custom_name}"' if custom_name else '""'
        
        # Construct the line protocol format for InfluxDB v1
        line = f"custom_data,host={host_id} custom_name={formatted_custom_name}"
        
        # Write to InfluxDB
        success = write_to_influxdb(line)
        
        if not success:
            return jsonify({"error": "Failed to update host name"}), 500
        
        return jsonify({
            "success": True,
            "message": "Host name updated successfully",
            "host": host_id,
            "customName": custom_name
        })
    except Exception as e:
        current_app.logger.error(f"Error updating host name: {e}")
        return jsonify({"error": str(e)}), 500

@hosts_bp.route('/<host_id>', methods=['DELETE'])
def delete_host(host_id):
    """Delete a host and all its data from InfluxDB."""
    if not host_id:
        return jsonify({"error": "Host ID is required"}), 400
    
    try:
        # Delete data from all measurements for this host
        measurements = [
            "cpu", "memory", "disk", "network", "uptime", 
            "ssh_sessions", "custom_data"
        ]
        
        for measurement in measurements:
            # For InfluxDB 1.x, we use DROP SERIES to delete points
            query = f'DROP SERIES FROM "{measurement}" WHERE "host" = \'{host_id}\''
            query_influxdb(query)
        
        return jsonify({
            "success": True,
            "message": f"Host '{host_id}' and all associated data successfully deleted"
        })
    except Exception as e:
        current_app.logger.error(f"Error deleting host {host_id}: {e}")
        return jsonify({"error": str(e)}), 500
