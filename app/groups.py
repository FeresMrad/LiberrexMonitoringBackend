"""Host groups management module for organizing hosts into logical groups."""
import os
import json
import uuid
from flask import current_app

# Path to the groups file
GROUPS_FILE = os.path.join('app', 'data', 'groups.json')

def ensure_groups_file():
    """Ensure the groups file exists, creating it with default structure if needed."""
    # Ensure the data directory exists
    os.makedirs(os.path.dirname(GROUPS_FILE), exist_ok=True)
    
    # If groups file doesn't exist, create it with empty structure
    if not os.path.exists(GROUPS_FILE):
        default_groups = {
            # Example group
            "default": {
                "id": "default",
                "name": "Default Group",
                "description": "Default group for all hosts",
                "hosts": []
            }
        }
        
        with open(GROUPS_FILE, 'w') as f:
            json.dump(default_groups, f, indent=4)
            
        current_app.logger.info(f"Created default groups file at {GROUPS_FILE}")
    
    return GROUPS_FILE

def load_groups():
    """Load all groups from the JSON file."""
    ensure_groups_file()
    
    try:
        with open(GROUPS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # If the file is corrupt, reset to defaults
        current_app.logger.error("Groups file is corrupted, resetting to defaults")
        os.remove(GROUPS_FILE)
        ensure_groups_file()
        with open(GROUPS_FILE, 'r') as f:
            return json.load(f)

def save_groups(groups):
    """Save the groups dictionary to the JSON file."""
    ensure_groups_file()
    
    with open(GROUPS_FILE, 'w') as f:
        json.dump(groups, f, indent=4)

def get_all_groups():
    """Get all host groups."""
    return load_groups()

def get_group_by_id(group_id):
    """Get a group by its ID."""
    groups = load_groups()
    return groups.get(group_id)

def get_group_by_name(name):
    """Get a group by its name."""
    groups = load_groups()
    
    for group_id, group in groups.items():
        if group.get('name') == name:
            return group
    
    return None

def create_group(name, description=None, hosts=None):
    """
    Create a new host group.
    
    Args:
        name: Group name
        description: Group description
        hosts: List of host IDs in the group
    """
    # Check if name is already in use
    if get_group_by_name(name):
        return False, "Group name already in use"
    
    # Generate a unique ID
    group_id = str(uuid.uuid4())
    
    # Set defaults for optional parameters
    if description is None:
        description = f"Group for {name}"
    if hosts is None:
        hosts = []
    
    # Create group object
    new_group = {
        "id": group_id,
        "name": name,
        "description": description,
        "hosts": hosts
    }
    
    # Add group to groups dictionary
    groups = load_groups()
    groups[group_id] = new_group
    save_groups(groups)
    
    return True, group_id

def update_group(group_id, updates):
    """
    Update a group's information.
    
    Args:
        group_id: ID of the group to update
        updates: Dictionary of fields to update
    """
    groups = load_groups()
    
    if group_id not in groups:
        return False, "Group not found"
    
    group = groups[group_id]
    
    # Handle rename - check if new name is already taken
    if 'name' in updates and updates['name'] != group['name']:
        existing = get_group_by_name(updates['name'])
        if existing and existing['id'] != group_id:
            return False, "Group name already in use"
    
    # Update fields
    for field, value in updates.items():
        if field != 'id':  # Don't allow id changes
            group[field] = value
    
    save_groups(groups)
    return True, "Group updated successfully"

def delete_group(group_id):
    """
    Delete a group.
    
    Args:
        group_id: ID of the group to delete
    """
    groups = load_groups()
    
    if group_id not in groups:
        return False, "Group not found"
    
    del groups[group_id]
    save_groups(groups)
    return True, "Group deleted successfully"

def add_host_to_group(group_id, host_id):
    """
    Add a host to a group.
    
    Args:
        group_id: ID of the group
        host_id: ID of the host to add
    """
    groups = load_groups()
    
    if group_id not in groups:
        return False, "Group not found"
    
    group = groups[group_id]
    
    # Check if host is already in the group
    if host_id in group['hosts']:
        return False, "Host is already in this group"
    
    # Add host to group
    group['hosts'].append(host_id)
    save_groups(groups)
    
    return True, "Host added to group successfully"

def remove_host_from_group(group_id, host_id):
    """
    Remove a host from a group.
    
    Args:
        group_id: ID of the group
        host_id: ID of the host to remove
    """
    groups = load_groups()
    
    if group_id not in groups:
        return False, "Group not found"
    
    group = groups[group_id]
    
    # Check if host is in the group
    if host_id not in group['hosts']:
        return False, "Host is not in this group"
    
    # Remove host from group
    group['hosts'].remove(host_id)
    save_groups(groups)
    
    return True, "Host removed from group successfully"

def get_host_groups(host_id):
    """
    Get all groups that a host belongs to.
    
    Args:
        host_id: ID of the host
    """
    groups = load_groups()
    host_groups = []
    
    for group_id, group in groups.items():
        if host_id in group.get('hosts', []):
            host_groups.append(group)
    
    return host_groups
