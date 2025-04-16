"""Authentication-related API endpoints."""
from flask import Blueprint, jsonify, request
from app.auth import authenticate_user, generate_token, validate_token

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
    
    # Generate JWT token with user info
    token = generate_token(user_data['email'])
    
    return jsonify({
        'token': token,
        'email': user_data['email']
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
    
    # Return user data from token - simplified
    return jsonify({
        'valid': True,
        'email': payload['user_id']
    })
