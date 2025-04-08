"""VictoriaLogs service module."""
import json
import requests
from flask import current_app


def query_victorialogs(query, start=None, end=None):
    """Execute a query against VictoriaLogs and return the results.
    
    Args:
        query: The VictoriaLogs query string
        start: Optional start time (e.g., '60m' for 60 minutes ago, or ISO datetime)
        end: Optional end time (ISO datetime)
        
    Returns:
        list: The parsed logs from VictoriaLogs
    """
    try:
        params = {"query": query}

        if start:
            params["start"] = start

        if end:
            params["end"] = end

        response = requests.get(
            f"{current_app.config['VICTORIALOGS_URL']}/select/logsql/query",
            params=params
        )
        response.raise_for_status()  # Raise exception for HTTP errors

        # Parse NDJSON response
        logs = []
        if response.text.strip():
            for line in response.text.strip().split('\n'):
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    current_app.logger.error(f"Error parsing log line: {line}")

        return logs
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error querying VictoriaLogs: {e}")
        return []
