"""Authentication module for JWT token generation and validation."""
import jwt
import datetime
from flask import current_app

# Static user list for demonstration - replace with database in production
USERS = {
    'admin@example.com': {
        'password': 'adminpass',
        'allowed_hosts': ['monitoring_server', 'web_server', 'database_server']
    },
    'user@example.com': {
        'password': 'userpass',
        'allowed_hosts': ['monitoring_server']
    }
}

def generate_token(user_id, allowed_hosts=None):
    """
    Generate a JWT token for WebSocket authentication.
    
    Args:
        user_id: The ID of the authenticated user
        allowed_hosts: List of hosts this user is allowed to access
        
    Returns:
        str: JWT token
    """
    payload = {
        'user_id': user_id,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1),
        'iat': datetime.datetime.utcnow(),
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
        
    # Authentication successful
    return True, {
        'email': email,
        'allowed_hosts': user_data['allowed_hosts']
    }
