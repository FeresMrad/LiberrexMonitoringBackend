"""Host groups management module for organizing hosts using MySQL database."""
import uuid
from flask import current_app
from app.mysql import get_db

def get_all_groups():
    """Get all host groups."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("SELECT id, name, description FROM host_groups")
    groups = cursor.fetchall()
    
    # Get hosts for each group
    for group in groups:
        cursor.execute("""
            SELECT host_id FROM group_hosts
            WHERE group_id = %s
        """, (group['id'],))
        
        hosts = [row['host_id'] for row in cursor.fetchall()]
        group['hosts'] = hosts
    
    cursor.close()
    
    # Convert to dictionary with ID as key for compatibility with old code
    groups_dict = {group['id']: group for group in groups}
    return groups_dict

def get_group_by_id(group_id):
    """Get a group by its ID."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, name, description FROM host_groups
        WHERE id = %s
    """, (group_id,))
    
    group = cursor.fetchone()
    
    if not group:
        cursor.close()
        return None
    
    # Get hosts for this group
    cursor.execute("""
        SELECT host_id FROM group_hosts
        WHERE group_id = %s
    """, (group_id,))
    
    hosts = [row['host_id'] for row in cursor.fetchall()]
    group['hosts'] = hosts
    
    cursor.close()
    return group

def get_group_by_name(name):
    """Get a group by its name."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, name, description FROM host_groups
        WHERE name = %s
    """, (name,))
    
    group = cursor.fetchone()
    
    if not group:
        cursor.close()
        return None
    
    # Get hosts for this group
    cursor.execute("""
        SELECT host_id FROM group_hosts
        WHERE group_id = %s
    """, (group['id'],))
    
    hosts = [row['host_id'] for row in cursor.fetchall()]
    group['hosts'] = hosts
    
    cursor.close()
    return group

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
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Insert group
        cursor.execute("""
            INSERT INTO host_groups (id, name, description)
            VALUES (%s, %s, %s)
        """, (group_id, name, description))
        
        # Add hosts to the group
        for host_id in hosts:
            cursor.execute("""
                INSERT INTO group_hosts (group_id, host_id)
                VALUES (%s, %s)
            """, (group_id, host_id))
        
        # Commit transaction
        db.commit()
        
        return True, group_id
    
    except Exception as e:
        current_app.logger.error(f"Error creating group: {e}")
        db.rollback()
        return False, str(e)

def update_group(group_id, updates):
    """
    Update a group's information.
    
    Args:
        group_id: ID of the group to update
        updates: Dictionary of fields to update
    """
    # Check if group exists
    group = get_group_by_id(group_id)
    if not group:
        return False, "Group not found"
    
    # Handle rename - check if new name is already taken
    if 'name' in updates and updates['name'] != group['name']:
        existing = get_group_by_name(updates['name'])
        if existing and existing['id'] != group_id:
            return False, "Group name already in use"
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Update fields
        if 'name' in updates:
            cursor.execute("""
                UPDATE host_groups SET name = %s
                WHERE id = %s
            """, (updates['name'], group_id))
        
        if 'description' in updates:
            cursor.execute("""
                UPDATE host_groups SET description = %s
                WHERE id = %s
            """, (updates['description'], group_id))
        
        # Update hosts if provided
        if 'hosts' in updates:
            # Replace all hosts - first remove existing
            cursor.execute("""
                DELETE FROM group_hosts
                WHERE group_id = %s
            """, (group_id,))
            
            # Then add new hosts
            for host_id in updates['hosts']:
                cursor.execute("""
                    INSERT INTO group_hosts (group_id, host_id)
                    VALUES (%s, %s)
                """, (group_id, host_id))
        
        # Commit transaction
        db.commit()
        
        return True, "Group updated successfully"
    
    except Exception as e:
        current_app.logger.error(f"Error updating group: {e}")
        db.rollback()
        return False, str(e)

def delete_group(group_id):
    """
    Delete a group.
    
    Args:
        group_id: ID of the group to delete
    """
    # Check if group exists
    group = get_group_by_id(group_id)
    if not group:
        return False, "Group not found"
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Delete group (foreign key constraints will automatically delete group_hosts entries)
        cursor.execute("""
            DELETE FROM host_groups
            WHERE id = %s
        """, (group_id,))
        
        # Commit transaction
        db.commit()
        
        return True, "Group deleted successfully"
    
    except Exception as e:
        current_app.logger.error(f"Error deleting group: {e}")
        db.rollback()
        return False, str(e)

def add_host_to_group(group_id, host_id):
    """
    Add a host to a group.
    
    Args:
        group_id: ID of the group
        host_id: ID of the host to add
    """
    # Check if group exists
    group = get_group_by_id(group_id)
    if not group:
        return False, "Group not found"
    
    # Check if host is already in the group
    if host_id in group['hosts']:
        return False, "Host is already in this group"
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Add host to group
        cursor.execute("""
            INSERT INTO group_hosts (group_id, host_id)
            VALUES (%s, %s)
        """, (group_id, host_id))
        
        # Commit transaction
        db.commit()
        
        return True, "Host added to group successfully"
    
    except Exception as e:
        current_app.logger.error(f"Error adding host to group: {e}")
        db.rollback()
        return False, str(e)

def remove_host_from_group(group_id, host_id):
    """
    Remove a host from a group.
    
    Args:
        group_id: ID of the group
        host_id: ID of the host to remove
    """
    # Check if group exists
    group = get_group_by_id(group_id)
    if not group:
        return False, "Group not found"
    
    # Check if host is in the group
    if host_id not in group['hosts']:
        return False, "Host is not in this group"
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Remove host from group
        cursor.execute("""
            DELETE FROM group_hosts
            WHERE group_id = %s AND host_id = %s
        """, (group_id, host_id))
        
        # Commit transaction
        db.commit()
        
        return True, "Host removed from group successfully"
    
    except Exception as e:
        current_app.logger.error(f"Error removing host from group: {e}")
        db.rollback()
        return False, str(e)

def get_host_groups(host_id):
    """
    Get all groups that a host belongs to.
    
    Args:
        host_id: ID of the host
    """
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT hg.id, hg.name, hg.description
        FROM host_groups hg
        JOIN group_hosts gh ON hg.id = gh.group_id
        WHERE gh.host_id = %s
    """, (host_id,))
    
    groups = cursor.fetchall()
    
    # Get hosts for each group
    for group in groups:
        cursor.execute("""
            SELECT host_id FROM group_hosts
            WHERE group_id = %s
        """, (group['id'],))
        
        hosts = [row['host_id'] for row in cursor.fetchall()]
        group['hosts'] = hosts
    
    cursor.close()
    return groups
