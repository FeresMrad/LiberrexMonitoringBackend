"""API endpoints for the monitoring application."""
import re
import json
from collections import Counter
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, current_app

from app.services.influxdb import query_influxdb, fetch_host_metric
from app.services.victorialogs import query_victorialogs

from app.auth import authenticate_user, generate_token

# Create a blueprint for the API
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Helper functions
def parse_time_parameters(request):
    """Parse time range parameters from the request."""
    start = request.args.get('start')
    end = request.args.get('end')
    time_range = request.args.get('timeRange')

    # If start and end are specified, they take precedence
    if start or end:
        return start, end

    # If timeRange is specified (e.g., '60m'), use that
    if time_range:
        return time_range, None

    # Default to 60 minutes if no parameters specified
    return '60m', None


def format_time_range_params(params, time_range):
    """Format time range parameters for API requests."""
    # If timeRange is an object with start/end
    if time_range and isinstance(time_range, dict):
        if time_range.get('start'):
            params['start'] = time_range['start']
        if time_range.get('end'):
            params['end'] = time_range['end']
    # If timeRange is a string (e.g., '60m')
    elif time_range:
        params['timeRange'] = time_range
    
    return params


# Host API Routes

@api_bp.route('/auth/login', methods=['POST'])
def login():
    """Authenticate user and return token."""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
        
    success, user_data = authenticate_user(email, password)
    
    if not success:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Generate JWT token with user info and permissions
    token = generate_token(
        user_data['email'], 
        is_admin=user_data.get('is_admin', False),
        allowed_hosts=user_data['allowed_hosts']
    )
    
    return jsonify({
        'token': token,
        'email': user_data['email'],
        'is_admin': user_data.get('is_admin', False),
        'allowed_hosts': user_data['allowed_hosts']
    })

@api_bp.route('/hosts', methods=['GET'])
def get_hosts():
    """Get all monitored hosts with basic metrics."""
    query = 'SHOW TAG VALUES WITH KEY = "host"'
    response = query_influxdb(query)

    hosts_data = []

    if response["results"][0].get("series"):
        for item in response["results"][0]["series"][0]["values"]:
            host_name = item[1]

            # Fetch host metrics
            host_data = {
                "name": host_name,
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


# Metrics API Routes
@api_bp.route('/metrics/<measurement>', methods=['GET'])
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

@api_bp.route('/metrics/specs', methods=['GET'])
def get_host_specs(host=None):
    """Get detailed specifications for a host."""
    # If host is not provided as an argument, get it from the request
    if host is None:
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


# Logs API Routes
@api_bp.route('/logs', methods=['GET'])
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


# SSH API Routes
@api_bp.route('/ssh/failed', methods=['GET'])
def get_ssh_failed():
    """Get count of failed SSH login attempts for a host."""
    host = request.args.get('host')

    if not host:
        return jsonify({"error": "Host parameter is required"}), 400

    start, end = parse_time_parameters(request)
    query = f'hostname:{host} app_name:sshd Failed password'
    logs = query_victorialogs(query, start, end)

    return jsonify({"count": len(logs)})


@api_bp.route('/ssh/failed/unique', methods=['GET'])
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


@api_bp.route('/ssh/failed/ips', methods=['GET'])
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


@api_bp.route('/ssh/failed/users', methods=['GET'])
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


@api_bp.route('/ssh/logs', methods=['GET'])
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


@api_bp.route('/ssh/sessions', methods=['GET'])
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


@api_bp.route('/ssh/accepted/users', methods=['GET'])
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


# Uptime API Routes
@api_bp.route('/uptime', methods=['GET'])
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


# Subscriptions debugging endpoint
@api_bp.route('/subscriptions', methods=['GET'])
def get_subscriptions():
    """Return information about current host subscriptions."""
    from app import host_subscribers
    
    result = {}
    for host, subscribers in host_subscribers.items():
        result[host] = len(subscribers)
    return jsonify(result)
