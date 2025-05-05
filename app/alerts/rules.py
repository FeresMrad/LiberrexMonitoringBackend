"""Alert rule management functions."""
import uuid
from datetime import datetime
from flask import current_app
from app.mysql import get_db

def get_all_rules():
    """Get all alert rules."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, name, description, metric_type, comparison, 
               threshold, duration_minutes, severity, enabled, created_at 
        FROM alert_rules
    """)
    
    rules = cursor.fetchall()
    
    # Get targets for each rule
    for rule in rules:
        rule['targets'] = get_rule_targets(rule['id'])
        rule['notifications'] = get_rule_notifications(rule['id'])
    
    cursor.close()
    return rules

def get_rules_for_measurement(measurement):
    """Get alert rules that apply to a specific measurement."""
    all_rules = get_all_rules()
    return [rule for rule in all_rules 
            if rule.get('enabled', False) and 
            rule['metric_type'].startswith(f"{measurement}.")]

def get_rule_by_id(rule_id):
    """Get an alert rule by its ID."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, name, description, metric_type, comparison, 
               threshold, duration_minutes, severity, enabled, created_at 
        FROM alert_rules 
        WHERE id = %s
    """, (rule_id,))
    
    rule = cursor.fetchone()
    
    if not rule:
        cursor.close()
        return None
    
    # Get targets for this rule
    rule['targets'] = get_rule_targets(rule_id)
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
    """Get notification settings for a rule."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT email_enabled, email_recipients 
        FROM alert_notifications 
        WHERE rule_id = %s
    """, (rule_id,))
    
    notifications = cursor.fetchone()
    cursor.close()
    
    return notifications or {'email_enabled': False, 'email_recipients': ''}

def create_rule(name, description, metric_type, comparison, threshold, 
                duration_minutes, severity, targets, notifications):
    """Create a new alert rule."""
    rule_id = str(uuid.uuid4())
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Insert rule
        cursor.execute("""
            INSERT INTO alert_rules 
            (id, name, description, metric_type, comparison, threshold, 
             duration_minutes, severity, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        """, (
            rule_id, name, description, metric_type, comparison, threshold,
            duration_minutes, severity
        ))
        
        # Insert targets
        for target in targets:
            cursor.execute("""
                INSERT INTO alert_targets (rule_id, target_type, target_id)
                VALUES (%s, %s, %s)
            """, (rule_id, target['type'], target['id']))
        
        # Insert notification settings
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
                                      'threshold', 'duration_minutes', 'severity', 'enabled']):
            fields = []
            params = []
            
            for field in ['name', 'description', 'metric_type', 'comparison', 
                         'threshold', 'duration_minutes', 'severity', 'enabled']:
                if field in updates:
                    fields.append(f"{field} = %s")
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
            notif = updates['notifications']
            cursor.execute("""
                INSERT INTO alert_notifications 
                (rule_id, email_enabled, email_recipients)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                email_enabled = VALUES(email_enabled),
                email_recipients = VALUES(email_recipients)
            """, (
                rule_id,
                notif.get('email_enabled', False),
                notif.get('email_recipients', '')
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
