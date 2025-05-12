"""User management module for storing and managing users in MySQL database."""
import uuid
from flask import current_app, g
from werkzeug.security import generate_password_hash, check_password_hash
from app.mysql import get_db

# Constant for super admin ID - explicitly defined for security checks
SUPER_ADMIN_ID = "admin"

def get_user_by_email(email):
    """Get a user by their email address."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, email, password_hash, name, role, has_wildcard_permission
        FROM users
        WHERE email = %s
    """, (email,))
    
    user = cursor.fetchone()
    cursor.close()
    
    if not user:
        return None
    
    # Add permissions to user data
    user['permissions'] = get_user_permissions(user['id'])
    
    return user

def get_user_by_id(user_id):
    """Get a user by their ID."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, email, password_hash, name, role, has_wildcard_permission
        FROM users
        WHERE id = %s
    """, (user_id,))
    
    user = cursor.fetchone()
    cursor.close()
    
    if not user:
        return None
    
    # Add permissions to user data
    user['permissions'] = get_user_permissions(user_id)
    
    return user

def is_super_admin(user_id):
    """Check if a user is the super admin."""
    return user_id == SUPER_ADMIN_ID

def get_user_permissions(user_id):
    """Get a user's permissions including host and group access."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Check user table directly for wildcard permission
    cursor.execute("""
        SELECT has_wildcard_permission FROM users
        WHERE id = %s AND has_wildcard_permission = TRUE
    """, (user_id,))
    
    wildcard = cursor.fetchone()
    
    if wildcard:
        # User has wildcard access to all hosts
        permissions = {"hosts": "*", "groups": []}
    else:
        # Get specific host permissions
        cursor.execute("""
            SELECT host_id FROM user_host_permissions
            WHERE user_id = %s
        """, (user_id,))
        
        host_permissions = [row['host_id'] for row in cursor.fetchall()]
        
        # Get group permissions
        cursor.execute("""
            SELECT group_id FROM user_group_permissions
            WHERE user_id = %s
        """, (user_id,))
        
        group_permissions = [row['group_id'] for row in cursor.fetchall()]
        
        permissions = {
            "hosts": host_permissions,
            "groups": group_permissions
        }
    
    cursor.close()
    return permissions

def create_user(email, password, name, role="user", permissions=None, creator_id=None):
    """
    Create a new user.
    
    Args:
        email: User's email address
        password: User's password
        name: User's display name
        role: User's role (user/admin)
        permissions: User's permissions
        creator_id: ID of the user creating this user (for permission checks)
    """
    # Check if email is already in use
    if get_user_by_email(email):
        return False, "Email already in use"
    
    # Only super admin can create admin users
    if role == "admin" and creator_id != SUPER_ADMIN_ID:
        return False, "Only the super administrator can create admin accounts"
    
    # Generate a unique ID
    user_id = str(uuid.uuid4())
    
    # Set default permissions if none provided
    if permissions is None:
        permissions = {"hosts": []}
    
    # Enforce permission structure based on role
    has_wildcard = False
    if role == "admin":
        has_wildcard = True  # Admin always gets full access
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Insert user with wildcard permission flag
        cursor.execute("""
            INSERT INTO users (id, email, password_hash, name, role, has_wildcard_permission)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            user_id,
            email,
            generate_password_hash(password),
            name,
            role,
            has_wildcard
        ))
        
        # No need to insert wildcard permission separately - it's now in the users table!
        
        # Add specific host permissions (if not using wildcard)
        if not has_wildcard:
            host_permissions = permissions.get('hosts', [])
            if isinstance(host_permissions, list):
                for host_id in host_permissions:
                    cursor.execute("""
                        INSERT INTO user_host_permissions (user_id, host_id)
                        VALUES (%s, %s)
                    """, (user_id, host_id))
        
        # Add group permissions
        group_permissions = permissions.get('groups', [])
        if isinstance(group_permissions, list):
            for group_id in group_permissions:
                cursor.execute("""
                    INSERT INTO user_group_permissions (user_id, group_id)
                    VALUES (%s, %s)
                """, (user_id, group_id))
        
        # Commit changes
        db.commit()
        
        return True, user_id
    
    except Exception as e:
        current_app.logger.error(f"Error creating user: {e}")
        db.rollback()
        return False, str(e)

def update_user(user_id, updates, modifier_id=None):
    """
    Update a user's information.
    
    Args:
        user_id: ID of the user to update
        updates: Dictionary of fields to update
        modifier_id: ID of the user making the change (for permission checks)
    """
    # Get the user to make sure they exist
    user = get_user_by_id(user_id)
    if not user:
        return False, "User not found"
    
    # Super admin protection
    if user_id == SUPER_ADMIN_ID:
        return False, "The super administrator account cannot be modified"
    
    # Only super admin can modify other admin accounts
    if user.get('role') == 'admin' and modifier_id != SUPER_ADMIN_ID:
        return False, "Only the super administrator can modify admin accounts"
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Create a copy of the updates to avoid modifying the original
        safe_updates = updates.copy()
        
        # Update user fields in the database
        if 'email' in safe_updates:
            cursor.execute("""
                UPDATE users SET email = %s
                WHERE id = %s
            """, (safe_updates['email'], user_id))
        
        if 'name' in safe_updates:
            cursor.execute("""
                UPDATE users SET name = %s
                WHERE id = %s
            """, (safe_updates['name'], user_id))
        
        if 'password' in safe_updates:
            cursor.execute("""
                UPDATE users SET password_hash = %s
                WHERE id = %s
            """, (generate_password_hash(safe_updates['password']), user_id))
        
        # Handle role changes
        if 'role' in safe_updates:
            cursor.execute("""
                UPDATE users SET role = %s
                WHERE id = %s
            """, (safe_updates['role'], user_id))
            
            # If user is becoming an admin, grant full permissions
            if safe_updates['role'] == 'admin':
                # Remove specific permissions
                cursor.execute("""
                    DELETE FROM user_host_permissions
                    WHERE user_id = %s
                """, (user_id,))
                
                # Set wildcard permission
                cursor.execute("""
                    UPDATE users SET has_wildcard_permission = TRUE
                    WHERE id = %s
                """, (user_id,))
        
        # Update permissions if provided
        if 'permissions' in safe_updates:
            update_user_permissions(user_id, safe_updates['permissions'], modifier_id)
        
        # Commit changes
        db.commit()
        
        return True, "User updated successfully"
    
    except Exception as e:
        current_app.logger.error(f"Error updating user: {e}")
        db.rollback()
        return False, str(e)

def delete_user(user_id, deleter_id=None):
    """
    Delete a user.
    
    Args:
        user_id: ID of the user to delete
        deleter_id: ID of the user performing the deletion (for permission checks)
    """
    # Get user to make sure they exist
    user = get_user_by_id(user_id)
    if not user:
        return False, "User not found"
    
    # Super admin protection
    if user_id == SUPER_ADMIN_ID:
        return False, "The super administrator account cannot be deleted"
    
    # Only super admin can delete admin accounts
    if user.get('role') == 'admin' and deleter_id != SUPER_ADMIN_ID:
        return False, "Only the super administrator can delete admin accounts"
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # If user is admin, check if they're the last admin
        if user.get('role') == 'admin':
            cursor.execute("""
                SELECT COUNT(*) as admin_count FROM users
                WHERE role = 'admin'
            """)
            result = cursor.fetchone()
            admin_count = result[0]
            
            if admin_count <= 1:
                return False, "Cannot delete the last admin user"
        
        # Delete user (foreign key constraints will cascade and delete permissions)
        cursor.execute("""
            DELETE FROM users
            WHERE id = %s
        """, (user_id,))
        
        # Commit changes
        db.commit()
        
        return True, "User deleted successfully"
    
    except Exception as e:
        current_app.logger.error(f"Error deleting user: {e}")
        db.rollback()
        return False, str(e)

def verify_password(email, password):
    """Verify a user's password."""
    user = get_user_by_email(email)
    
    if not user:
        return False, None
    
    if check_password_hash(user['password_hash'], password):
        return True, user
    
    return False, None

def update_user_permissions(user_id, permissions, modifier_id=None):
    """
    Update a user's permissions.
    
    Args:
        user_id: ID of the user to update
        permissions: New permissions
        modifier_id: ID of the user making the change (for permission checks)
    """
    # Get user to make sure they exist
    user = get_user_by_id(user_id)
    if not user:
        return False, "User not found"
    
    # Super admin protection
    if user_id == SUPER_ADMIN_ID:
        return False, "The super administrator's permissions cannot be modified"
    
    # Only super admin can modify admin permissions
    if user.get('role') == 'admin' and modifier_id != SUPER_ADMIN_ID:
        return False, "Only the super administrator can modify admin permissions"
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Clear existing permissions
        cursor.execute("DELETE FROM user_host_permissions WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM user_group_permissions WHERE user_id = %s", (user_id,))
        
        # Admin users always get full access
        if user.get('role') == 'admin':
            cursor.execute("""
                UPDATE users SET has_wildcard_permission = TRUE
                WHERE id = %s
            """, (user_id,))
        else:
            # Set new permissions
            if permissions.get('hosts') == '*':
                # Set wildcard permission
                cursor.execute("""
                    UPDATE users SET has_wildcard_permission = TRUE
                    WHERE id = %s
                """, (user_id,))
            else:
                # Set specific host permissions
                cursor.execute("""
                    UPDATE users SET has_wildcard_permission = FALSE
                    WHERE id = %s
                """, (user_id,))
                
                if isinstance(permissions.get('hosts'), list):
                    for host_id in permissions['hosts']:
                        cursor.execute("""
                            INSERT INTO user_host_permissions (user_id, host_id)
                            VALUES (%s, %s)
                        """, (user_id, host_id))
        
        # Commit changes
        db.commit()
        
        return True, "Permissions updated successfully"
    
    except Exception as e:
        current_app.logger.error(f"Error updating permissions: {e}")
        db.rollback()
        return False, str(e)

def can_access_host(user_id, host_id):
    """Check if a user can access a specific host."""
    # Get the user
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
    if host_id in user.get('permissions', {}).get('hosts', []):
        return True
    
    # Check for access through groups
    db = get_db()
    cursor = db.cursor()
    
    # This query checks if the user has access to any group that contains the host
    cursor.execute("""
        SELECT 1 FROM user_group_permissions ugp
        JOIN group_hosts gh ON ugp.group_id = gh.group_id
        WHERE ugp.user_id = %s AND gh.host_id = %s
    """, (user_id, host_id))
    
    result = cursor.fetchone()
    cursor.close()
    
    return result is not None

def get_all_users():
    """Get all users with sensitive information removed."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, email, name, role, has_wildcard_permission
        FROM users
    """)
    
    users = cursor.fetchall()
    cursor.close()
    
    # Add permissions to each user
    for user in users:
        user['permissions'] = get_user_permissions(user['id'])
        # Convert has_wildcard to boolean 
        user['has_wildcard'] = bool(user.get('has_wildcard'))
    
    return users
