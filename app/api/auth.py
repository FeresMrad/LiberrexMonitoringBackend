"""Authentication-related API endpoints."""
from flask import Blueprint, jsonify, request
from app.auth import authenticate_user, generate_token, validate_token, get_user_by_id

# Create a blueprint for auth endpoints
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['POST'])
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
    
    # Get the full user object to generate token
    user = get_user_by_id(user_data['id'])
    
    # Generate JWT token with user info
    token = generate_token(user)
    
    return jsonify({
        'token': token,
        'user': {
            'id': user_data['id'],
            'email': user_data['email'],
            'name': user_data.get('name', ''),
            'role': user_data.get('role', 'user')
        }
    })

@auth_bp.route('/validate', methods=['POST', 'OPTIONS'])
def validate_token_endpoint():
    """Validate a JWT token."""
    # Handle preflight CORS request
    if request.method == 'OPTIONS':
        return '', 204
    
    data = request.get_json()
    token = data.get('token')
    
    if not token:
        return jsonify({'error': 'Token is required'}), 400
        
    # Validate token using the existing validate_token function
    payload = validate_token(token)
    
    if not payload:
        return jsonify({'error': 'Invalid token'}), 401
    
    # Return user data from token
    return jsonify({
        'valid': True,
        'user': {
            'id': payload.get('user_id'),
            'email': payload.get('email'),
            'role': payload.get('role', 'user')
        }
    })
