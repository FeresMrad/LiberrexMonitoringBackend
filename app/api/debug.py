"""Debug and administrative API endpoints."""
from flask import Blueprint, jsonify

# Create a blueprint for debug endpoints
debug_bp = Blueprint('debug', __name__, url_prefix='/debug')

@debug_bp.route('/subscriptions', methods=['GET'])
def get_subscriptions():
    """Return information about current host subscriptions."""
    from app import host_subscribers
    
    result = {}
    for host, subscribers in host_subscribers.items():
        result[host] = len(subscribers)
    return jsonify(result)
