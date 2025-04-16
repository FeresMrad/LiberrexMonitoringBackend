"""Utility functions for the API endpoints."""
from flask import request

# These utility functions were refactored from the original app/api.py
# and are shared across multiple API modules

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
