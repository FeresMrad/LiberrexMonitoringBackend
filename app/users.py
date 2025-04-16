"""User management module for storing and managing users in a JSON file."""
import os
import json
import uuid
from flask import current_app
from werkzeug.security import generate_password_hash, check_password_hash

# Path to the users file
USERS_FILE = os.path.join('app', 'data', 'users.json')

# Default admin user
DEFAULT_ADMIN = {
    "id": "admin",
    "email": "admin@example.com",
    "password_hash": generate_password_hash("adminpass"),
    "role": "admin",
    "name": "Administrator",
    "permissions": {
        "hosts": "*"  # Asterisk means access to all hosts
    }
}

# Default user
DEFAULT_USER = {
    "id": "user",
    "email": "user@example.com",
    "password_hash": generate_password_hash("userpass"),
    "role": "user",
    "name": "Regular User",
    "permissions": {
        "hosts": []  # Empty list means no access to any hosts
    }
}

def ensure_users_file():
    """Ensure the users file exists, creating it with default users if needed."""
    # Ensure the data directory exists
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    
    # If users file doesn't exist, create it with default users
    if not os.path.exists(USERS_FILE):
        default_users = {
            "admin": DEFAULT_ADMIN,
            "user": DEFAULT_USER
        }
        
        with open(USERS_FILE, 'w') as f:
            json.dump(default_users, f, indent=4)
            
        current_app.logger.info(f"Created default users file at {USERS_FILE}")
    
    return USERS_FILE

def load_users():
    """Load all users from the JSON file."""
    ensure_users_file()
    
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # If the file is corrupt, reset to defaults
        current_app.logger.error("Users file is corrupted, resetting to defaults")
        os.remove(USERS_FILE)
        ensure_users_file()
        with open(USERS_FILE, 'r') as f:
            return json.load(f)

def save_users(users):
    """Save the users dictionary to the JSON file."""
    ensure_users_file()
    
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def get_user_by_email(email):
    """Get a user by their email address."""
    users = load_users()
    
    for user_id, user in users.items():
        if user.get('email') == email:
            return user
    
    return None

def get_user_by_id(user_id):
    """Get a user by their ID."""
    users = load_users()
    return users.get(user_id)

def create_user(email, password, name, role="user", permissions=None):
    """Create a new user."""
    # Check if email is already in use
    if get_user_by_email(email):
        return False, "Email already in use"
    
    # Generate a unique ID
    user_id = str(uuid.uuid4())
    
    # Set default permissions if none provided
    if permissions is None:
        permissions = {"hosts": []}
    
    # Create user object
    new_user = {
        "id": user_id,
        "email": email,
        "password_hash": generate_password_hash(password),
        "role": role,
        "name": name,
        "permissions": permissions
    }
    
    # Add user to users dictionary
    users = load_users()
    users[user_id] = new_user
    save_users(users)
    
    return True, user_id

def update_user(user_id, updates):
    """Update a user's information."""
    users = load_users()
    
    if user_id not in users:
        return False, "User not found"
    
    user = users[user_id]
    
    # Update user fields
    for field, value in updates.items():
        if field == 'password':
            user['password_hash'] = generate_password_hash(value)
        elif field != 'password_hash' and field != 'id':  # Don't allow direct password_hash or id changes
            user[field] = value
    
    save_users(users)
    return True, "User updated successfully"

def delete_user(user_id):
    """Delete a user."""
    users = load_users()
    
    if user_id not in users:
        return False, "User not found"
    
    # Prevent deleting the last admin
    if users[user_id].get('role') == 'admin':
        admin_count = sum(1 for u in users.values() if u.get('role') == 'admin')
        if admin_count <= 1:
            return False, "Cannot delete the last admin user"
    
    del users[user_id]
    save_users(users)
    return True, "User deleted successfully"

def verify_password(email, password):
    """Verify a user's password."""
    user = get_user_by_email(email)
    
    if not user:
        return False, None
    
    if check_password_hash(user['password_hash'], password):
        return True, user
    
    return False, None

def get_user_permissions(user_id):
    """Get a user's permissions."""
    user = get_user_by_id(user_id)
    
    if not user:
        return None
    
    return user.get('permissions', {})

def update_user_permissions(user_id, permissions):
    """Update a user's permissions."""
    users = load_users()
    
    if user_id not in users:
        return False, "User not found"
    
    users[user_id]['permissions'] = permissions
    save_users(users)
    return True, "Permissions updated successfully"

def can_access_host(user_id, host_id):
    """Check if a user can access a specific host."""
    user = get_user_by_id(user_id)
    
    if not user:
        return False
    
    # Admin role has access to everything
    if user.get('role') == 'admin':
        return True
    
    # Check for wildcard access
    if user.get('permissions', {}).get('hosts') == '*':
        return True
    
    # Check for specific host access
    return host_id in user.get('permissions', {}).get('hosts', [])

def get_all_users():
    """Get all users with sensitive information removed."""
    users = load_users()
    
    # Create a new dictionary with sensitive info removed
    safe_users = {}
    for user_id, user in users.items():
        safe_users[user_id] = {
            "id": user_id,
            "email": user.get('email'),
            "name": user.get('name'),
            "role": user.get('role'),
            "permissions": user.get('permissions', {})
        }
    
    return safe_users
