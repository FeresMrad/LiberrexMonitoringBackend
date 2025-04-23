"""Apache-related API endpoints."""
from flask import Blueprint, jsonify, request
from app.services.influxdb import query_influxdb
from .utils import parse_time_parameters

# Create a blueprint for Apache endpoints
apache_bp = Blueprint('apache', __name__, url_prefix='/apache')

@apache_bp.route('/rps', methods=['GET'])
def get_apache_rps():
    """Get Apache requests per second metrics for a host."""
    host = request.args.get('host')
    
    if not host:
        return jsonify({"error": "Host parameter is required"}), 400
    
    # Parse time range parameters 
    start, end = parse_time_parameters(request)
    
    # Build queries for both apache_raw and apache_interval
    raw_query = f'SELECT "req_per_sec" FROM "apache_raw" WHERE host=\'{host}\''
    interval_query = f'SELECT "interval_req_per_sec" FROM "apache_interval" WHERE host=\'{host}\''
    
    # Add time range if specified
    if start and not end:
        # If only start is specified as a relative time (e.g., '1h')
        raw_query += f' AND time > now() - {start}'
        interval_query += f' AND time > now() - {start}'
    elif start and end:
        # If both start and end are specified as ISO timestamps
        raw_query += f' AND time >= \'{start}\' AND time <= \'{end}\''
        interval_query += f' AND time >= \'{start}\' AND time <= \'{end}\''
    
    # Add sorting
    raw_query += ' ORDER BY time ASC'
    interval_query += ' ORDER BY time ASC'
    
    # Execute queries
    raw_response = query_influxdb(raw_query)
    interval_response = query_influxdb(interval_query)
    
    # Process responses
    results = []
    
    # Create a dictionary to store the time points and values
    time_points = {}
    
    # Process raw data
    if raw_response["results"][0].get("series"):
        raw_values = raw_response["results"][0]["series"][0]["values"]
        for value in raw_values:
            time_str = value[0]
            req_per_sec = value[1]
            
            if time_str not in time_points:
                time_points[time_str] = {"time": time_str, "req_per_sec": req_per_sec}
            else:
                time_points[time_str]["req_per_sec"] = req_per_sec
    
    # Process interval data
    if interval_response["results"][0].get("series"):
        interval_values = interval_response["results"][0]["series"][0]["values"]
        for value in interval_values:
            time_str = value[0]
            interval_req_per_sec = value[1]
            
            if time_str not in time_points:
                time_points[time_str] = {"time": time_str, "interval_req_per_sec": interval_req_per_sec}
            else:
                time_points[time_str]["interval_req_per_sec"] = interval_req_per_sec
    
    # Convert the dictionary to a list and sort by time
    for time_str, data in time_points.items():
        # Ensure both metrics exist in each data point, fill with null if missing
        if "req_per_sec" not in data:
            data["req_per_sec"] = None
        if "interval_req_per_sec" not in data:
            data["interval_req_per_sec"] = None
        results.append(data)
    
    # Sort by time
    results.sort(key=lambda x: x["time"])
    
    return jsonify(results)

@apache_bp.route('/status', methods=['GET'])
def get_apache_status():
    """Get Apache server status information."""
    host = request.args.get('host')
    
    if not host:
        return jsonify({"error": "Host parameter is required"}), 400
    
    # Get the latest values for apache status
    query = f'''
        SELECT 
            busy_workers, idle_workers, uptime_seconds, 
            total_accesses, total_kbytes, bytes_per_req, 
            bytes_per_sec, duration_per_req
        FROM apache_raw 
        WHERE host='{host}' 
        ORDER BY time DESC 
        LIMIT 1
    '''
    
    response = query_influxdb(query)
    
    # Check if we got a result
    if not response["results"][0].get("series"):
        return jsonify({"error": "No Apache data found for this host"}), 404
    
    # Get column names and values
    columns = response["results"][0]["series"][0]["columns"]
    values = response["results"][0]["series"][0]["values"][0]
    
    # Build result object
    result = {
        "timestamp": values[0]  # First column is always the timestamp
    }
    
    # Add all other columns
    for i in range(1, len(columns)):
        result[columns[i]] = values[i]
    
    # Check if Apache is responsive
    health_query = f'''
        SELECT is_responsive
        FROM apache_health
        WHERE host='{host}'
        ORDER BY time DESC
        LIMIT 1
    '''
    
    health_response = query_influxdb(health_query)
    
    if health_response["results"][0].get("series"):
        health_values = health_response["results"][0]["series"][0]["values"][0]
        result["is_responsive"] = health_values[1] == 1
    else:
        result["is_responsive"] = False
    
    return jsonify(result)

@apache_bp.route('/bpr', methods=['GET'])
def get_apache_bpr():
    """Get Apache bytes per request metrics for a host."""
    host = request.args.get('host')
    
    if not host:
        return jsonify({"error": "Host parameter is required"}), 400
    
    # Parse time range parameters 
    start, end = parse_time_parameters(request)
    
    # Build queries for both apache_raw and apache_interval
    raw_query = f'SELECT "bytes_per_req" FROM "apache_raw" WHERE host=\'{host}\''
    interval_query = f'SELECT "interval_bytes_per_req" FROM "apache_interval" WHERE host=\'{host}\''
    
    # Add time range if specified
    if start and not end:
        # If only start is specified as a relative time (e.g., '1h')
        raw_query += f' AND time > now() - {start}'
        interval_query += f' AND time > now() - {start}'
    elif start and end:
        # If both start and end are specified as ISO timestamps
        raw_query += f' AND time >= \'{start}\' AND time <= \'{end}\''
        interval_query += f' AND time >= \'{start}\' AND time <= \'{end}\''
    
    # Add sorting
    raw_query += ' ORDER BY time ASC'
    interval_query += ' ORDER BY time ASC'
    
    # Execute queries
    raw_response = query_influxdb(raw_query)
    interval_response = query_influxdb(interval_query)
    
    # Process responses
    results = []
    
    # Create a dictionary to store the time points and values
    time_points = {}
    
    # Process raw data
    if raw_response["results"][0].get("series"):
        raw_values = raw_response["results"][0]["series"][0]["values"]
        for value in raw_values:
            time_str = value[0]
            bytes_per_req = value[1]
            
            if time_str not in time_points:
                time_points[time_str] = {"time": time_str, "bytes_per_req": bytes_per_req}
            else:
                time_points[time_str]["bytes_per_req"] = bytes_per_req
    
    # Process interval data
    if interval_response["results"][0].get("series"):
        interval_values = interval_response["results"][0]["series"][0]["values"]
        for value in interval_values:
            time_str = value[0]
            interval_bytes_per_req = value[1]
            
            if time_str not in time_points:
                time_points[time_str] = {"time": time_str, "interval_bytes_per_req": interval_bytes_per_req}
            else:
                time_points[time_str]["interval_bytes_per_req"] = interval_bytes_per_req
    
    # Convert the dictionary to a list and sort by time
    for time_str, data in time_points.items():
        # Ensure both metrics exist in each data point, fill with null if missing
        if "bytes_per_req" not in data:
            data["bytes_per_req"] = None
        if "interval_bytes_per_req" not in data:
            data["interval_bytes_per_req"] = None
        results.append(data)
    
    # Sort by time
    results.sort(key=lambda x: x["time"])
    
    return jsonify(results)
