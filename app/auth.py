"""Authentication module for JWT token generation and validation."""
import jwt
import datetime
from flask import current_app

# Static user list for demonstration - simplified structure
USERS = {
    'admin@example.com': 'adminpass',
    'user@example.com': 'userpass'
}

def generate_token(user_id):
    """
    Generate a JWT token for WebSocket authentication.
    
    Args:
        user_id: The ID of the authenticated user
        
    Returns:
        str: JWT token
    """
    payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1),
        'iat': datetime.datetime.utcnow()
    }
    
    return jwt.encode(
        payload,
        current_app.config['SECRET_KEY'],
        algorithm='HS256'
    )

def validate_token(token):
    """
    Validate a JWT token.
    
    Args:
        token: The JWT token to validate
        
    Returns:
        dict: The decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            current_app.config['SECRET_KEY'],
            algorithms=['HS256']
        )
        return payload
    except jwt.ExpiredSignatureError:
        # Token has expired
        return None
    except jwt.InvalidTokenError:
        # Token is invalid
        return None

def authenticate_user(email, password):
    """
    Authenticate a user with email and password.
    
    Args:
        email: User's email
        password: User's password
        
    Returns:
        tuple: (success, user_data) - success is boolean, user_data contains user information
    """
    stored_password = USERS.get(email)
    
    if not stored_password or stored_password != password:
        return False, None
    
    # Authentication successful - simplified
    return True, {'email': email}

def get_all_hosts():
    """
    Return all hosts in the system.
    
    Returns:
        list: List of all hosts in the system
    """
    # Get all available hosts from InfluxDB
    from app.services.influxdb import query_influxdb
    query = 'SHOW TAG VALUES FROM "cpu" WITH KEY = "host"'
    
    response = query_influxdb(query)
    
    if response["results"][0].get("series"):
        return [item[1] for item in response["results"][0]["series"][0]["values"]]
    return []
