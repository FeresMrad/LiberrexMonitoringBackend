"""InfluxDB service module."""
import requests
from flask import current_app


def query_influxdb(query):
    """Execute a query against InfluxDB and return the results.
    
    Args:
        query: The InfluxDB query string to execute
        
    Returns:
        dict: The JSON response from InfluxDB
    """
    try:
        response = requests.get(
            f"{current_app.config['INFLUXDB_URL']}/query",
            params={
                "db": current_app.config['INFLUXDB_DATABASE'],
                "q": query,
                "u": current_app.config['INFLUXDB_USER'],
                "p": current_app.config['INFLUXDB_PASSWORD'],
            }
        )
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error querying InfluxDB: {e}")
        return {"results": [{"series": []}]}


def fetch_host_metric(host, measurement, field, retries=3):
    """Fetch a specific metric for a host.
    
    Args:
        host: The hostname to query
        measurement: The measurement name in InfluxDB
        field: The field to retrieve
        retries: Number of retry attempts
        
    Returns:
        The value of the requested field or 0 if not found
    """
    query = f'SELECT "{field}" FROM "{measurement}" WHERE "host" = \'{host}\' ORDER BY time DESC LIMIT 1'

    for attempt in range(retries):
        response = query_influxdb(query)

        if response["results"][0].get("series"):
            return response["results"][0]["series"][0]["values"][0][1]

        # If we failed but have retries left, wait briefly
        if attempt < retries - 1:
            import time
            time.sleep(1)

    return 0  # Default value if all retries fail1~"""InfluxDB service module."""
import requests
from flask import current_app


def query_influxdb(query):
    """Execute a query against InfluxDB and return the results.
    
    Args:
        query: The InfluxDB query string to execute
        
    Returns:
        dict: The JSON response from InfluxDB
    """
    try:
        response = requests.get(
            f"{current_app.config['INFLUXDB_URL']}/query",
            params={
                "db": current_app.config['INFLUXDB_DATABASE'],
                "q": query,
                "u": current_app.config['INFLUXDB_USER'],
                "p": current_app.config['INFLUXDB_PASSWORD'],
            }
        )
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json()
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error querying InfluxDB: {e}")
        return {"results": [{"series": []}]}


def fetch_host_metric(host, measurement, field, retries=3):
    """Fetch a specific metric for a host.
    
    Args:
        host: The hostname to query
        measurement: The measurement name in InfluxDB
        field: The field to retrieve
        retries: Number of retry attempts
        
    Returns:
        The value of the requested field or 0 if not found
    """
    query = f'SELECT "{field}" FROM "{measurement}" WHERE "host" = \'{host}\' ORDER BY time DESC LIMIT 1'

    for attempt in range(retries):
        response = query_influxdb(query)

        if response["results"][0].get("series"):
            return response["results"][0]["series"][0]["values"][0][1]

        # If we failed but have retries left, wait briefly
        if attempt < retries - 1:
            import time
            time.sleep(1)

    return 0  # Default value if all retries fail

def write_to_influxdb(line):
    """Write data to InfluxDB using line protocol.
    
    Args:
        line: The line protocol string to write
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        response = requests.post(
            f"{current_app.config['INFLUXDB_URL']}/write",
            params={
                "db": current_app.config['INFLUXDB_DATABASE'],
                "u": current_app.config['INFLUXDB_USER'],
                "p": current_app.config['INFLUXDB_PASSWORD'],
            },
            data=line
        )
        response.raise_for_status()  # Raise exception for HTTP errors
        return True
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error writing to InfluxDB: {e}")
        return False
