"""Authentication module for JWT token generation and validation."""
import jwt
import datetime
from flask import current_app

# Static user list for demonstration - replace with database in production
USERS = {
    'admin@example.com': {
        'password': 'adminpass',
        'is_admin': True,
        'allowed_hosts': []  # Empty list for admin, will get access to all hosts
    },
    'user@example.com': {
        'password': 'userpass',
        'is_admin': False,
        'allowed_hosts': ['monitoring_server']
    }
}

def generate_token(user_id, is_admin=False, allowed_hosts=None):
    """
    Generate a JWT token for WebSocket authentication.
    
    Args:
        user_id: The ID of the authenticated user
        is_admin: Boolean indicating if user has admin privileges
        allowed_hosts: List of hosts this user is allowed to access
        
    Returns:
        str: JWT token
    """
    payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1),
        'iat': datetime.datetime.utcnow(),
        'is_admin': is_admin,
        'allowed_hosts': allowed_hosts or []
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
    user_data = USERS.get(email)
    
    if not user_data:
        return False, None
        
    if user_data['password'] != password:
        return False, None
    
    # Get all available hosts for admin users
    is_admin = user_data.get('is_admin', False)
    allowed_hosts = user_data['allowed_hosts']
    
    # Authentication successful
    return True, {
        'email': email,
        'is_admin': is_admin,
        'allowed_hosts': allowed_hosts
    }

def get_accessible_hosts(payload):
    """
    Determine which hosts the user can access based on their token.
    For admin users, dynamically fetch all available hosts.
    
    Args:
        payload: The decoded JWT token payload
        
    Returns:
        list: List of hosts the user can access
    """
    # If the user is an admin, they can access all hosts
    if payload.get('is_admin', False):
        # Get all available hosts from InfluxDB
        # This could be implemented in various ways depending on your setup
        from app.services.influxdb import query_influxdb
        query = 'SHOW TAG VALUES WITH KEY = "host"'
        response = query_influxdb(query)
        
        all_hosts = []
        if response["results"][0].get("series"):
            all_hosts = [item[1] for item in response["results"][0]["series"][0]["values"]]
        
        return all_hosts
    
    # For regular users, return their specifically allowed hosts
    return payload.get('allowed_hosts', [])
