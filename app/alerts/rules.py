"""Simplified alert rule management functions."""
import uuid
from flask import current_app
from app.mysql import get_db

def get_all_rules():
    """Get all alert rules."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, name, description, metric_type, comparison, 
               threshold, enabled, created_at, severity
        FROM alert_rules
    """)
    
    rules = cursor.fetchall()
    
    # Get targets for each rule
    for rule in rules:
        rule['targets'] = get_rule_targets(rule['id'])
        
        # Convert enabled from tinyint to boolean for clarity
        if 'enabled' in rule:
            rule['enabled'] = bool(rule['enabled'])
        
        # Get notification settings
        rule['notifications'] = get_rule_notifications(rule['id'])
    
    cursor.close()
    return rules

def get_rules_for_measurement(measurement):
    """Get alert rules that apply to a specific measurement."""
    all_rules = get_all_rules()
    # Filter rules: must be enabled and match the measurement type
    enabled_rules = [rule for rule in all_rules 
                    if rule.get('enabled', False) is True and 
                    rule['metric_type'].startswith(f"{measurement}.")]
    
    current_app.logger.info(f"Found {len(enabled_rules)} enabled rules out of {len(all_rules)} total rules for measurement {measurement}")
    return enabled_rules

def get_rule_by_id(rule_id):
    """Get an alert rule by its ID."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, name, description, metric_type, comparison, 
               threshold, enabled, created_at, severity 
        FROM alert_rules 
        WHERE id = %s
    """, (rule_id,))
    
    rule = cursor.fetchone()
    
    if not rule:
        cursor.close()
        return None
    
    # Get targets for this rule
    rule['targets'] = get_rule_targets(rule_id)
    
    # Convert enabled from tinyint to boolean for clarity
    if 'enabled' in rule:
        rule['enabled'] = bool(rule['enabled'])
    
    # Get notification settings
    rule['notifications'] = get_rule_notifications(rule_id)
    
    cursor.close()
    return rule

def get_rule_targets(rule_id):
    """Get targets for a specific rule."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT target_type, target_id 
        FROM alert_targets 
        WHERE rule_id = %s
    """, (rule_id,))
    
    targets = cursor.fetchall()
    cursor.close()
    
    return targets

def get_rule_notifications(rule_id):
    """Get notification settings for a specific rule."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT email_enabled, email_recipients
        FROM alert_notifications
        WHERE rule_id = %s
    """, (rule_id,))
    
    notification = cursor.fetchone()
    cursor.close()
    
    if not notification:
        return {
            'email_enabled': False,
            'email_recipients': ''
        }
    
    # Convert tinyint to boolean
    notification['email_enabled'] = bool(notification['email_enabled'])
    return notification

def create_rule(name, description, metric_type, comparison, threshold, targets, severity='warning'):
    """Create a new alert rule."""
    rule_id = str(uuid.uuid4())
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Insert rule - explicitly set enabled to TRUE
        cursor.execute("""
            INSERT INTO alert_rules 
            (id, name, description, metric_type, comparison, threshold, enabled, severity, duration_minutes)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, 0)
        """, (
            rule_id, name, description, metric_type, comparison, threshold, severity
        ))
        
        # Insert targets
        for target in targets:
            cursor.execute("""
                INSERT INTO alert_targets (rule_id, target_type, target_id)
                VALUES (%s, %s, %s)
            """, (rule_id, target['type'], target['id']))
        
        # Create default notifications
        cursor.execute("""
            INSERT INTO alert_notifications (rule_id, email_enabled, email_recipients)
            VALUES (%s, FALSE, '')
        """, (rule_id,))
        
        db.commit()
        current_app.logger.info(f"Created new rule {rule_id} with enabled=TRUE")
        return rule_id
    except Exception as e:
        current_app.logger.error(f"Error creating alert rule: {e}")
        db.rollback()
        raise

def update_rule(rule_id, updates):
    """Update an existing alert rule."""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Update basic rule properties
        if any(k in updates for k in ['name', 'description', 'metric_type', 'comparison', 
                                      'threshold', 'enabled', 'severity']):
            fields = []
            params = []
            
            for field in ['name', 'description', 'metric_type', 'comparison', 
                         'threshold', 'enabled', 'severity']:
                if field in updates:
                    fields.append(f"{field} = %s")
                    # Log when enabled status is changed
                    if field == 'enabled':
                        current_app.logger.info(f"Updating rule {rule_id} enabled status to {updates[field]}")
                    params.append(updates[field])
            
            if fields:
                query = f"UPDATE alert_rules SET {', '.join(fields)} WHERE id = %s"
                params.append(rule_id)
                cursor.execute(query, params)
        
        # Update targets if provided
        if 'targets' in updates:
            # Delete existing targets
            cursor.execute("DELETE FROM alert_targets WHERE rule_id = %s", (rule_id,))
            
            # Insert new targets
            for target in updates['targets']:
                cursor.execute("""
                    INSERT INTO alert_targets (rule_id, target_type, target_id)
                    VALUES (%s, %s, %s)
                """, (rule_id, target['type'], target['id']))
        
        # Update notifications if provided
        if 'notifications' in updates:
            notifications = updates['notifications']
            
            # Check if notification settings already exist
            cursor.execute("SELECT 1 FROM alert_notifications WHERE rule_id = %s", (rule_id,))
            exists = cursor.fetchone()
            
            if exists:
                # Update existing
                cursor.execute("""
                    UPDATE alert_notifications
                    SET email_enabled = %s, email_recipients = %s
                    WHERE rule_id = %s
                """, (
                    notifications.get('email_enabled', False),
                    notifications.get('email_recipients', ''),
                    rule_id
                ))
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO alert_notifications
                    (rule_id, email_enabled, email_recipients)
                    VALUES (%s, %s, %s)
                """, (
                    rule_id,
                    notifications.get('email_enabled', False),
                    notifications.get('email_recipients', '')
                ))
        
        db.commit()
        return True
    except Exception as e:
        current_app.logger.error(f"Error updating alert rule: {e}")
        db.rollback()
        return False

def delete_rule(rule_id):
    """Delete an alert rule."""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Delete the rule (cascade will handle related tables)
        cursor.execute("DELETE FROM alert_rules WHERE id = %s", (rule_id,))
        
        db.commit()
        return True
    except Exception as e:
        current_app.logger.error(f"Error deleting alert rule: {e}")
        db.rollback()
        return False
