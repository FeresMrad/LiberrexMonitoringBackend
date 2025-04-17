"""Host group management API endpoints."""
from flask import Blueprint, jsonify, request
from app.groups import (
    get_all_groups, get_group_by_id, create_group, update_group, 
    delete_group, add_host_to_group, remove_host_from_group, get_host_groups
)
from app.auth import require_admin, require_auth

# Create a blueprint for group endpoints
groups_bp = Blueprint('groups', __name__, url_prefix='/groups')

@groups_bp.route('', methods=['GET'])
@require_auth
def get_groups():
    """Get all host groups."""
    groups = get_all_groups()
    return jsonify(list(groups.values()))

@groups_bp.route('/<group_id>', methods=['GET'])
@require_auth
def get_group(group_id):
    """Get a specific group."""
    group = get_group_by_id(group_id)
    
    if not group:
        return jsonify({"error": "Group not found"}), 404
    
    return jsonify(group)

@groups_bp.route('', methods=['POST'])
@require_admin
def add_group():
    """Create a new group (admin only)."""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Required fields
    name = data.get('name')
    
    if not name:
        return jsonify({"error": "Group name is required"}), 400
    
    # Optional fields
    description = data.get('description')
    hosts = data.get('hosts', [])
    color = data.get('color')
    
    # Create group
    success, result = create_group(name, description, hosts, color)
    
    if not success:
        return jsonify({"error": result}), 400
    
    return jsonify({"success": True, "group_id": result}), 201

@groups_bp.route('/<group_id>', methods=['PUT'])
@require_admin
def update_group_info(group_id):
    """Update a group (admin only)."""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Check if group exists
    group = get_group_by_id(group_id)
    if not group:
        return jsonify({"error": "Group not found"}), 404
    
    # Update group
    success, message = update_group(group_id, data)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({"success": True, "message": message})

@groups_bp.route('/<group_id>', methods=['DELETE'])
@require_admin
def remove_group(group_id):
    """Delete a group (admin only)."""
    success, message = delete_group(group_id)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({"success": True, "message": message})

@groups_bp.route('/<group_id>/hosts/<host_id>', methods=['POST'])
@require_admin
def add_host(group_id, host_id):
    """Add a host to a group (admin only)."""
    success, message = add_host_to_group(group_id, host_id)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({"success": True, "message": message})

@groups_bp.route('/<group_id>/hosts/<host_id>', methods=['DELETE'])
@require_admin
def remove_host(group_id, host_id):
    """Remove a host from a group (admin only)."""
    success, message = remove_host_from_group(group_id, host_id)
    
    if not success:
        return jsonify({"error": message}), 400
    
    return jsonify({"success": True, "message": message})

@groups_bp.route('/hosts/<host_id>', methods=['GET'])
@require_auth
def get_groups_for_host(host_id):
    """Get all groups that a host belongs to."""
    host_groups = get_host_groups(host_id)
    return jsonify(host_groups)
