"""User management API endpoints."""
from flask import Blueprint, jsonify, request
from app.users import (
    get_all_users, get_user_by_id, create_user, update_user, 
    delete_user, update_user_permissions, SUPER_ADMIN_ID
)
from app.auth import require_admin, require_auth, get_all_hosts

# Create a blueprint for user endpoints
users_bp = Blueprint('users', __name__, url_prefix='/users')

@users_bp.route('', methods=['GET'])
@require_admin
def get_users():
    """Get all users (admin only)."""
    users = get_all_users()
    return jsonify(list(users.values()))

@users_bp.route('/<user_id>', methods=['GET'])
@require_admin
def get_user(user_id):
    """Get a specific user (admin only)."""
    user = get_user_by_id(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Remove sensitive information
    user_data = {
        "id": user.get('id'),
        "email": user.get('email'),
        "name": user.get('name'),
        "role": user.get('role'),
        "permissions": user.get('permissions', {})
    }
    
    return jsonify(user_data)

@users_bp.route('', methods=['POST'])
@require_admin
def add_user():
    """Create a new user (admin only)."""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Required fields
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    
    if not email or not password or not name:
        return jsonify({"error": "Email, password, and name are required"}), 400
    
    # Optional fields
    role = data.get('role', 'user')
    permissions = data.get('permissions', {"hosts": []})
    
    # Validate role
    if role not in ['admin', 'user']:
        return jsonify({"error": "Invalid role"}), 400
    
    # Get the creator ID for permission checks
    creator_id = request.user.get('user_id')
    
    # Create user
    success, result = create_user(email, password, name, role, permissions, creator_id)
    
    if not success:
        return jsonify({"error": result}), 400
    
    return jsonify({"success": True, "user_id": result}), 201

@users_bp.route('/<user_id>', methods=['PUT'])
@require_admin
def update_user_info(user_id):
    """Update a user (admin only)."""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Check if user exists
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Get the modifier ID for permission checks
    modifier_id = request.user.get('user_id')
    
    # Update user
    success, message = update_user(user_id, data, modifier_id)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({"success": True, "message": message})

@users_bp.route('/<user_id>', methods=['DELETE'])
@require_admin
def remove_user(user_id):
    """Delete a user (admin only)."""
    # Get the deleter ID for permission checks
    deleter_id = request.user.get('user_id')
    
    success, message = delete_user(user_id, deleter_id)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({"success": True, "message": message})

@users_bp.route('/<user_id>/permissions', methods=['PUT'])
@require_admin
def set_user_permissions(user_id):
    """Update a user's permissions (admin only)."""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Check if user exists
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Get the modifier ID for permission checks
    modifier_id = request.user.get('user_id')
    
    # Update permissions
    success, message = update_user_permissions(user_id, data, modifier_id)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({"success": True, "message": message})

@users_bp.route('/me', methods=['GET'])
@require_auth
def get_current_user():
    """Get the current authenticated user's profile."""
    user_id = request.user.get('user_id')
    user = get_user_by_id(user_id)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Return only necessary information
    user_data = {
        "id": user.get('id'),
        "email": user.get('email'),
        "name": user.get('name'),
        "role": user.get('role'),
        "isSuperAdmin": user_id == SUPER_ADMIN_ID  # Add this flag for frontend checking
    }
    
    return jsonify(user_data)

@users_bp.route('/hosts', methods=['GET'])
@require_auth
def get_available_hosts():
    """Get all hosts available in the system with indication of access."""
    user_id = request.user.get('user_id')
    
    # Get all hosts from the system
    all_hosts = get_all_hosts()
    
    # Get user's permissions
    user = get_user_by_id(user_id)
    is_admin = user.get('role') == 'admin'
    
    # Get the groups that the user has access to
    user_groups = user.get('permissions', {}).get('groups', [])
    
    # Determine host access
    host_access = []
    
    if is_admin or user.get('permissions', {}).get('hosts') == '*':
        # Admin or wildcard access - all hosts are accessible
        host_access = [{"host": host, "access": True, "accessType": "direct"} for host in all_hosts]
    else:
        # Regular user - check access for each host
        direct_access_hosts = user.get('permissions', {}).get('hosts', [])
        
        # Get hosts accessible through groups
        from app.groups import get_host_groups
        
        for host in all_hosts:
            # Check direct access
            if host in direct_access_hosts:
                host_access.append({
                    "host": host, 
                    "access": True,
                    "accessType": "direct"
                })
                continue
            
            # Check access through groups
            host_groups = get_host_groups(host)
            group_access = False
            for group in host_groups:
                if group['id'] in user_groups:
                    host_access.append({
                        "host": host, 
                        "access": True,
                        "accessType": "group",
                        "groupId": group['id'],
                        "groupName": group['name']
                    })
                    group_access = True
                    break
            
            # No access
            if not group_access and host not in direct_access_hosts:
                host_access.append({
                    "host": host, 
                    "access": False,
                    "accessType": "none"
                })
    
    return jsonify(host_access)
