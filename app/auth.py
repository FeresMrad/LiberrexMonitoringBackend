"""Authentication module for JWT token generation and validation."""
import jwt
import datetime
from flask import current_app, request, jsonify
from functools import wraps
from app.users import verify_password, get_user_by_id, can_access_host, get_user_permissions

def generate_token(user):
    """
    Generate a JWT token for WebSocket authentication.
    
    Args:
        user: The authenticated user object
        
    Returns:
        str: JWT token
    """
    payload = {
        'user_id': user['id'],
        'email': user['email'],
        'role': user['role'],
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
    success, user = verify_password(email, password)
    
    if not success or not user:
        return False, None
    
    # Return only necessary user information (exclude password hash)
    user_data = {
        'id': user['id'],
        'email': user['email'],
        'name': user.get('name', ''),
        'role': user.get('role', 'user')
    }
    
    return True, user_data

def require_auth(f):
    """
    Decorator for routes that require authentication.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'Authorization header is required'}), 401
        
        # Check for Bearer token format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({'error': 'Authorization header must be in format "Bearer token"'}), 401
        
        token = parts[1]
        payload = validate_token(token)
        
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Add user info to request for use in route handler
        request.user = payload
        
        return f(*args, **kwargs)
    
    return decorated

def require_admin(f):
    """
    Decorator for routes that require admin role.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # First check authentication
        auth_result = require_auth(lambda: None)()
        if isinstance(auth_result, tuple) and auth_result[1] != 200:
            return auth_result
        
        # Then check admin role
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin role required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated

def host_access_required(f):
    """
    Decorator for routes that require access to a specific host.
    The host parameter must be included in the route parameters or query string.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # First check authentication
        auth_result = require_auth(lambda: None)()
        if isinstance(auth_result, tuple) and auth_result[1] != 200:
            return auth_result
        
        # Get host from route parameters or query string
        host = kwargs.get('host') or request.args.get('host')
        
        if not host:
            return jsonify({'error': 'Host parameter is required'}), 400
        
        # Check if user has access to this host
        if not can_access_host(request.user.get('user_id'), host):
            return jsonify({'error': 'You do not have access to this host'}), 403
        
        return f(*args, **kwargs)
    
    return decorated

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

def get_accessible_hosts(user_id):
    """
    Get the list of hosts a user can access.
    
    Args:
        user_id: The user ID
        
    Returns:
        list: List of hosts the user can access
    """
    user = get_user_by_id(user_id)
    
    if not user:
        return []
    
    # Admin or wildcard permissions can access all hosts
    if user.get('role') == 'admin' or user.get('permissions', {}).get('hosts') == '*':
        return get_all_hosts()
    
    # Return only the hosts the user has explicit access to
    # that actually exist in the system
    all_hosts = get_all_hosts()
    user_hosts = user.get('permissions', {}).get('hosts', [])
    
    return [host for host in all_hosts if host in user_hosts]
