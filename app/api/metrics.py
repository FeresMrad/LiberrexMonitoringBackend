"""Metrics-related API endpoints."""
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app
from app.services.influxdb import query_influxdb

# Create a blueprint for metrics endpoints
metrics_bp = Blueprint('metrics', __name__, url_prefix='/metrics')

@metrics_bp.route('/<measurement>', methods=['GET'])
def get_metrics(measurement):
    """Get metrics for a specific measurement type."""
    host = request.args.get('host')
    time_range = request.args.get('timeRange')
    latest_only = request.args.get('latest', 'false').lower() == 'true'

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    # Build query based on the measurement type
    if measurement == 'cpu':
        field = 'percent'
        if latest_only:
            query = f'SELECT {field} FROM {measurement} WHERE host=\'{host}\' ORDER BY time DESC LIMIT 1'
        else:
            query = f'SELECT {field} FROM {measurement} WHERE host=\'{host}\''
    elif measurement == 'memory':
        field = 'percent'
        if latest_only:
            query = f'SELECT {field} FROM {measurement} WHERE host=\'{host}\' ORDER BY time DESC LIMIT 1'
        else:
            query = f'SELECT {field} FROM {measurement} WHERE host=\'{host}\''
    elif measurement == 'disk':
        if latest_only:
            query = f'SELECT percent, disk_read_per_second, disk_write_per_second FROM {measurement} WHERE host=\'{host}\' ORDER BY time DESC LIMIT 1'
        else:
            query = f'SELECT percent, disk_read_per_second, disk_write_per_second FROM {measurement} WHERE host=\'{host}\''
    elif measurement == 'network':
        if latest_only:
            query = f'SELECT sent_per_second, received_per_second FROM {measurement} WHERE host=\'{host}\' ORDER BY time DESC LIMIT 1'
        else:
            query = f'SELECT sent_per_second, received_per_second FROM {measurement} WHERE host=\'{host}\''
    elif measurement == 'specs':
        # Special case for specs - we need to make multiple queries
        return get_host_specs(host)
    else:
        return jsonify({"error": f"Invalid measurement type: {measurement}"}), 400

    # Add time range if specified and not requesting latest only
    if time_range and time_range != 'all' and not latest_only:
        query += f' AND time > now() - {time_range} ORDER BY time ASC'
    elif not latest_only:
        # If no time range specified and not latest only, add default sorting
        query += ' ORDER BY time ASC'

    response = query_influxdb(query)

    # Process the response based on the measurement type
    if not response["results"][0].get("series"):
        # Return an empty list for time series or an empty object for latest only
        return jsonify([] if not latest_only else {})

    values = response["results"][0]["series"][0]["values"]
    columns = response["results"][0]["series"][0]["columns"]

    # If we're only interested in the latest value, return it as a single object
    if latest_only:
        result = {}
        for i, column in enumerate(columns[1:], 1):
            # For disk and network measurements, convert bytes to KB
            if measurement in ['disk', 'network'] and column in ['disk_read_per_second', 'disk_write_per_second', 'sent_per_second', 'received_per_second']:
                result[column] = values[0][i] / 1024 if values[0][i] is not None else 0
            else:
                result[column] = values[0][i]
        
        # Add the timestamp
        result['time'] = values[0][0]
        return jsonify(result)
    
    # Convert to a list of dictionaries for easier consumption by the frontend
    results = []
    for value in values:
        result = {"time": value[0]}
        for i, column in enumerate(columns[1:], 1):
            # For disk and network measurements, convert bytes to KB
            if measurement in ['disk', 'network'] and column in ['disk_read_per_second', 'disk_write_per_second', 'sent_per_second', 'received_per_second']:
                result[column] = value[i] / 1024 if value[i] is not None else 0
            else:
                result[column] = value[i]
        results.append(result)

    return jsonify(results)

@metrics_bp.route('/specs', methods=['GET'])
def get_host_specs():
    """Get detailed specifications for a host."""
    host = request.args.get('host')
    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    try:
        # Memory query
        memory_query = f'SELECT total-available, total FROM memory WHERE host=\'{host}\' ORDER BY time DESC LIMIT 1'
        memory_response = query_influxdb(memory_query)

        # Disk query
        disk_query = f'SELECT used, total FROM disk WHERE host=\'{host}\' ORDER BY time DESC LIMIT 1'
        disk_response = query_influxdb(disk_query)

        # IP address query
        ip_query = f'SELECT ip_adr FROM network WHERE host=\'{host}\' ORDER BY time DESC LIMIT 1'
        ip_response = query_influxdb(ip_query)

        # Uptime query
        uptime_query = f'SELECT uptime_seconds FROM uptime WHERE host=\'{host}\' ORDER BY time DESC LIMIT 1'
        uptime_response = query_influxdb(uptime_query)

        # Process memory data
        memory_current = 0
        memory_max = 0
        if memory_response["results"][0].get("series"):
            memory_values = memory_response["results"][0]["series"][0]["values"][0]
            memory_current = memory_values[1] / 1e9 if memory_values[1] is not None else 0
            memory_max = memory_values[2] / 1e9 if memory_values[2] is not None else 0

        # Process disk data
        disk_current = 0
        disk_max = 0
        if disk_response["results"][0].get("series"):
            disk_values = disk_response["results"][0]["series"][0]["values"][0]
            disk_current = disk_values[1] / 1e9 if disk_values[1] is not None else 0
            disk_max = disk_values[2] / 1e9 if disk_values[2] is not None else 0

        # Process IP address
        ip_address = "Unknown"
        if ip_response["results"][0].get("series"):
            ip_values = ip_response["results"][0]["series"][0]["values"][0]
            ip_address = ip_values[1] if ip_values[1] is not None else "Unknown"

        # Process uptime/boot time
        boot_time = "Unknown"
        if uptime_response["results"][0].get("series"):
            uptime_values = uptime_response["results"][0]["series"][0]["values"][0]
            uptime_seconds = uptime_values[1] if uptime_values[1] is not None else 0

            # Calculate system boot time
            boot_timestamp = datetime.now().timestamp() - uptime_seconds
            boot_time = datetime.fromtimestamp(boot_timestamp).strftime('%d/%m/%Y, %H:%M:%S')

        specs = {
            "memoryCurrent": memory_current,
            "memoryMax": memory_max,
            "diskCurrent": disk_current,
            "diskMax": disk_max,
            "ipAddress": ip_address,
            "uptime": boot_time
        }

        return jsonify(specs)

    except Exception as e:
        current_app.logger.error(f"Error in get_host_specs: {e}")
        return jsonify({"error": str(e)}), 500
