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
               threshold, enabled, created_at, breach_count,
               email_threshold, email_breach_count, sms_threshold, sms_breach_count
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
    
    return enabled_rules

def get_rule_by_id(rule_id):
    """Get an alert rule by its ID."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT id, name, description, metric_type, comparison, 
               threshold, enabled, created_at, breach_count,
               email_threshold, email_breach_count, sms_threshold, sms_breach_count
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
        SELECT email_enabled, email_recipients, sms_enabled, sms_recipients
        FROM alert_notifications
        WHERE rule_id = %s
    """, (rule_id,))
    
    notification = cursor.fetchone()
    cursor.close()
    
    if not notification:
        return {
            'email_enabled': False,
            'email_recipients': '',
            'sms_enabled': False,
            'sms_recipients': ''
        }
    
    # Convert tinyint to boolean
    notification['email_enabled'] = bool(notification['email_enabled'])
    notification['sms_enabled'] = bool(notification['sms_enabled'])
    return notification

def create_rule(name, description, metric_type, comparison, threshold, targets, 
                min_breach_count=1, email_threshold=None, 
                email_breach_count=None, sms_threshold=None, sms_breach_count=None):
    """Create a new alert rule."""
    rule_id = str(uuid.uuid4())
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Insert rule with the new SMS threshold fields
        cursor.execute("""
            INSERT INTO alert_rules 
            (id, name, description, metric_type, comparison, threshold, enabled, 
             breach_count, email_threshold, email_breach_count, 
             sms_threshold, sms_breach_count)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s)
        """, (
            rule_id, name, description, metric_type, comparison, threshold, 
            min_breach_count, email_threshold, email_breach_count,
            sms_threshold, sms_breach_count
        ))
        
        # Create default notifications
        cursor.execute("""
            INSERT INTO alert_notifications (rule_id, email_enabled, email_recipients, sms_enabled, sms_recipients)
            VALUES (%s, FALSE, '', FALSE, '')
        """, (rule_id,))
        
        db.commit()
        current_app.logger.info(f"Created new rule {rule_id} with enabled=TRUE, min_breach_count={min_breach_count}")
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
                                     'threshold', 'enabled', 'min_breach_count',
                                     'email_threshold', 'email_breach_count', 'sms_threshold', 'sms_breach_count']):
            fields = []
            params = []
            
            for field in ['name', 'description', 'metric_type', 'comparison', 
                         'threshold', 'enabled']:
                if field in updates:
                    fields.append(f"{field} = %s")
                    # Log when enabled status is changed
                    if field == 'enabled':
                        current_app.logger.info(f"Updating rule {rule_id} enabled status to {updates[field]}")
                    params.append(updates[field])
            
            # Handle min_breach_count by updating breach_count
            if 'min_breach_count' in updates:
                fields.append("breach_count = %s")
                params.append(updates['min_breach_count'])
                current_app.logger.info(f"Updating rule {rule_id} min_breach_count to {updates['min_breach_count']}")
            
            # Handle email threshold fields
            if 'email_threshold' in updates:
                fields.append("email_threshold = %s")
                params.append(updates['email_threshold'])
                
            if 'email_breach_count' in updates:
                fields.append("email_breach_count = %s")
                params.append(updates['email_breach_count'])

            # Handle SMS threshold fields
            if 'sms_threshold' in updates:
                fields.append("sms_threshold = %s")
                params.append(updates['sms_threshold'])
    
            if 'sms_breach_count' in updates:
                fields.append("sms_breach_count = %s")
                params.append(updates['sms_breach_count'])

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
                    SET email_enabled = %s, email_recipients = %s, sms_enabled = %s, sms_recipients =  %s
                    WHERE rule_id = %s
                """, (
                    notifications.get('email_enabled', False),
                    notifications.get('email_recipients', ''),
                    notifications.get('sms_enabled', False),
                    notifications.get('sms_recipients',''),
                    rule_id
                ))
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO alert_notifications
                    (rule_id, email_enabled, email_recipients, sms_enabled, sms_recipients)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    rule_id,
                    notifications.get('email_enabled', False),
                    notifications.get('email_recipients', ''),
                    notifcations.get('sms_enabled', False),
                    notifications.get('sms_recipients', '')
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
