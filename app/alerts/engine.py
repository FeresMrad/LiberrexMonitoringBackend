"""Simplified alert detection and evaluation engine."""
import uuid
from flask import current_app
import datetime
from app.mysql import get_db
from app.alerts.rules import get_all_rules, get_rules_for_measurement
from app.alerts.notification import send_email_alert, send_sms_alert

# Global in-memory store for last seen values and breach tracking
# Format: {rule_id: {host: {'last_value': value, 'last_check': timestamp, 'breach_count': 0, 'email_breach_count': 0}}}
alert_state = {}

def host_matches_rule(rule, host):
    """Check if a host is targeted by this rule."""
    # Check each target in the rule
    for target in rule.get('targets', []):
        if target['target_type'] == 'all':
            return True
        elif target['target_type'] == 'host' and target['target_id'] == host:
            return True
    return False

def is_threshold_breached(rule, value, threshold=None):
    """Check if a value breaches the threshold according to the comparison type."""
    comparison = rule['comparison']
    
    # Use provided threshold or fallback to rule's main threshold
    threshold_value = threshold if threshold is not None else float(rule['threshold'])
    
    if comparison == 'above':
        return value > threshold_value
    elif comparison == 'below':
        return value < threshold_value
    elif comparison == 'equal':
        return value == threshold_value
    else:
        return False

def record_last_value(rule, host, value, timestamp):
    """Record the last value and update breach count for a host/rule combination."""
    rule_id = rule['id']
    
    # Initialize state tracking for this rule and host if needed
    if rule_id not in alert_state:
        alert_state[rule_id] = {}
        
    if host not in alert_state[rule_id]:
        alert_state[rule_id][host] = {
            'last_value': None, 
            'last_check': None, 
            'breach_count': 0,
            'sms_breach_count': 0,
            'last_sms_sent': None,
            'last_email_sent': None,
            'email_breach_count': 0  # New counter for email threshold breaches
        }
    
    # Get the minimum breach count needed for main threshold
    min_breach_count = rule.get('breach_count')  # Default to 1 if not specified or zero
    
    # Check if main threshold is breached
    is_breached = is_threshold_breached(rule, value)
    
    if is_breached:
        # Increment breach count for main threshold
        alert_state[rule_id][host]['breach_count'] += 1
        current_app.logger.info(f"Breach count for rule {rule_id}, host {host}: {alert_state[rule_id][host]['breach_count']}/{min_breach_count}")
    else:
        # Reset breach count if threshold is no longer breached
        if alert_state[rule_id][host]['breach_count'] > 0:
            current_app.logger.info(f"Resetting breach count for rule {rule_id}, host {host}")
            alert_state[rule_id][host]['breach_count'] = 0
    
    # Also check email threshold if configured
    check_email_threshold_breach(rule, host, value)
    
    # Check SMS threshold if configured
    check_sms_threshold_breach(rule, host, value)

    # Update with new value
    alert_state[rule_id][host]['last_value'] = value
    alert_state[rule_id][host]['last_check'] = timestamp

def check_email_threshold_breach(rule, host, value):
    """Check and update email threshold breach count."""
    rule_id = rule['id']
    
    # Only process if email notification is enabled and threshold is set
    notifications = rule.get('notifications', {})
    if not notifications.get('email_enabled', False) or rule.get('email_threshold') is None:
        return
    
    # Get the email threshold value
    email_threshold = float(rule['email_threshold'])
    
    # Get the minimum breach count needed for email notifications
    email_min_breach_count = rule.get('email_breach_count')
    
    # Check if email threshold is breached
    is_email_breached = is_threshold_breached(rule, value, email_threshold)
    
    if is_email_breached:
        # Increment email breach count
        alert_state[rule_id][host]['email_breach_count'] += 1
        current_app.logger.info(
            f"Email breach count for rule {rule_id}, host {host}: "
            f"{alert_state[rule_id][host]['email_breach_count']}/{email_min_breach_count}"
        )
    else:
        # Reset email breach count if threshold is no longer breached
        if alert_state[rule_id][host].get('email_breach_count', 0) > 0:
            current_app.logger.info(f"Resetting email breach count for rule {rule_id}, host {host}")
            alert_state[rule_id][host]['email_breach_count'] = 0

def is_email_alert_triggered(rule, host):
    """Check if email alert conditions are met (both threshold and duration)."""
    rule_id = rule['id']
    
    # Only proceed if email notification is enabled and threshold is set
    notifications = rule.get('notifications', {})
    if not notifications.get('email_enabled', False) or rule.get('email_threshold') is None:
        return False
    
    # Check if we have state for this rule/host
    if rule_id not in alert_state or host not in alert_state[rule_id]:
        return False
    
    # Get current breach count and required minimum
    current_count = alert_state[rule_id][host].get('email_breach_count', 0)
    required_count = rule.get('email_breach_count')
    
    # Email alert is triggered if we've reached the required breach count
    return current_count == required_count

def check_sms_threshold_breach(rule, host, value):
    """Check and update SMS threshold breach count."""
    rule_id = rule['id']
    
    # Only process if SMS notification is enabled and threshold is set
    notifications = rule.get('notifications', {})
    if not notifications.get('sms_enabled', False) or rule.get('sms_threshold') is None:
        return
    
    # Get the SMS threshold value
    sms_threshold = float(rule['sms_threshold'])
    
    # Get the minimum breach count needed for SMS notifications
    sms_min_breach_count = rule.get('sms_breach_count')
    
    # Check if SMS threshold is breached
    is_sms_breached = is_threshold_breached(rule, value, sms_threshold)
    
    if is_sms_breached:
        # Increment SMS breach count
        alert_state[rule_id][host]['sms_breach_count'] += 1
        current_app.logger.info(
            f"SMS breach count for rule {rule_id}, host {host}: "
            f"{alert_state[rule_id][host]['sms_breach_count']}/{sms_min_breach_count}"
        )
    else:
        # Reset SMS breach count if threshold is no longer breached
        if alert_state[rule_id][host].get('sms_breach_count', 0) > 0:
            current_app.logger.info(f"Resetting SMS breach count for rule {rule_id}, host {host}")
            alert_state[rule_id][host]['sms_breach_count'] = 0

def is_sms_alert_triggered(rule, host):
    """Check if SMS alert conditions are met (both threshold and duration)."""
    rule_id = rule['id']
    
    # Only proceed if SMS notification is enabled and threshold is set
    notifications = rule.get('notifications', {})
    if not notifications.get('sms_enabled', False) or rule.get('sms_threshold') is None:
        return False
    
    # Check if we have state for this rule/host
    if rule_id not in alert_state or host not in alert_state[rule_id]:
        return False
    
    # Get current breach count and required minimum
    current_count = alert_state[rule_id][host].get('sms_breach_count', 0)
    required_count = rule.get('sms_breach_count')
    
    # SMS alert is triggered if we've reached the required breach count
    return current_count == required_count

def handle_alert_trigger(rule, host, value, is_email_alert=False, is_sms_alert=False):
    """Handle the alert trigger by creating a new alert event."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Check if there's already an active alert for this rule and host
    cursor.execute("""
        SELECT id FROM alert_events
        WHERE rule_id = %s AND host = %s AND status = 'triggered'
        ORDER BY triggered_at DESC LIMIT 1
    """, (rule['id'], host))
    
    existing_alert = cursor.fetchone()
    
    if existing_alert:
        # Alert already exists, don't create a new one
        alert_id = existing_alert['id']
        current_app.logger.info(f"Alert already exists for rule {rule['id']}, host {host} - not creating duplicate")
        message = generate_alert_message(rule, host, value, is_email=is_email_alert, is_sms=is_sms_alert)
        
        # If this is an email alert trigger for an existing alert,
        # we still want to send the email notification
        # Send email notifications if email is enabled
        if is_email_alert or (rule.get('email_threshold') is None and rule.get('notifications', {}).get('email_enabled', False)):
            send_email_for_existing_alert(rule, host, value, alert_id, message)

        # Send SMS notifications if SMS is enabled
        if is_sms_alert or (rule.get('sms_threshold') is None and rule.get('notifications', {}).get('sms_enabled', False)):
            send_sms_for_existing_alert(rule, host, value, alert_id, message)
        cursor.close()
        return
    
    # Create a new alert
    alert_id = str(uuid.uuid4())
    message = generate_alert_message(rule, host, value, is_email=is_email_alert)
    
    try:
        current_app.logger.info(f"Inserting new alert with ID {alert_id} for rule {rule['id']}, host {host}")
        cursor.execute("""
            INSERT INTO alert_events
            (id, rule_id, host, status, value, message)
            VALUES (%s, %s, %s, 'triggered', %s, %s)
        """, (alert_id, rule['id'], host, value, message))
        
        # Create notifications for all users
        create_notifications_for_alert(cursor, alert_id, rule)
        
        db.commit()
        current_app.logger.info(f"Successfully inserted alert with ID {alert_id}")
        
        # Send WebSocket notifications to connected users
        send_alert_websocket_notification(alert_id, rule, host, value, message)
        
        # Send email notifications (if configured and triggered)
        if is_email_alert or (rule.get('email_threshold') is None and rule.get('notifications', {}).get('email_enabled', False)):
            send_email_alert(rule, host, value, message)

        # Send SMS notifications (if configured and triggered)
        if is_sms_alert or (rule.get('sms_threshold') is None and rule.get('notifications', {}).get('sms_enabled', False)):
            send_sms_alert(rule, host, value, message)

    except Exception as e:
        current_app.logger.error(f"Database error inserting alert: {e}", exc_info=True)
        db.rollback()
    finally:
        cursor.close()

def send_email_for_existing_alert(rule, host, value, alert_id, message):
    """Send an email notification for an existing alert with cooldown period."""
    try:
        # Add a new dictionary to track alerts if it doesn't exist
        if 'alert_cooldowns' not in alert_state:
            alert_state['alert_cooldowns'] = {}
            
        cooldown_minutes = 30
        current_time = datetime.datetime.now()
        
        # Check cooldown using alert_id as the key
        if (alert_id in alert_state['alert_cooldowns'] and 
            alert_state['alert_cooldowns'][alert_id].get('last_email_sent')):
            
            last_sent = alert_state['alert_cooldowns'][alert_id]['last_email_sent']
            time_diff = (current_time - last_sent).total_seconds() / 60
            
            if time_diff < cooldown_minutes:
                current_app.logger.info(
                    f"Skipping email for alert {alert_id} - cooldown period not elapsed "
                    f"({time_diff:.1f}/{cooldown_minutes} minutes)"
                )
                return
                
        # Send the email
        current_app.logger.info(f"Sending email for existing alert {alert_id}")
        send_email_alert(rule, host, value, message)
        
        # Update the last sent timestamp using alert_id
        if 'alert_cooldowns' in alert_state:
            if alert_id not in alert_state['alert_cooldowns']:
                alert_state['alert_cooldowns'][alert_id] = {}
            alert_state['alert_cooldowns'][alert_id]['last_email_sent'] = current_time
            
    except Exception as e:
        current_app.logger.error(f"Error sending email for existing alert: {e}", exc_info=True)

def send_sms_for_existing_alert(rule, host, value, alert_id, message):
    """Send an SMS notification for an existing alert with cooldown period."""
    try:
        # Add a new dictionary to track alerts if it doesn't exist
        if 'alert_cooldowns' not in alert_state:
            alert_state['alert_cooldowns'] = {}
            
        cooldown_minutes = 30
        current_time = datetime.datetime.now()
        
        # Check cooldown using alert_id as the key
        if (alert_id in alert_state['alert_cooldowns'] and 
            alert_state['alert_cooldowns'][alert_id].get('last_sms_sent')):
            
            last_sent = alert_state['alert_cooldowns'][alert_id]['last_sms_sent']
            time_diff = (current_time - last_sent).total_seconds() / 60
            
            if time_diff < cooldown_minutes:
                current_app.logger.info(
                    f"Skipping SMS for alert {alert_id} - cooldown period not elapsed "
                    f"({time_diff:.1f}/{cooldown_minutes} minutes)"
                )
                return
                
        # Send the SMS
        current_app.logger.info(f"Sending SMS for existing alert {alert_id}")
        send_sms_alert(rule, host, value, message)
        
        # Update the last sent timestamp using alert_id
        if 'alert_cooldowns' in alert_state:
            if alert_id not in alert_state['alert_cooldowns']:
                alert_state['alert_cooldowns'][alert_id] = {}
            alert_state['alert_cooldowns'][alert_id]['last_sms_sent'] = current_time
            
    except Exception as e:
        current_app.logger.error(f"Error sending SMS for existing alert: {e}", exc_info=True)

def create_notifications_for_alert(cursor, alert_id, rule):
    """Create notifications for all users who should be notified about this alert."""
    # Get all users
    cursor.execute("SELECT id FROM users")
    users = cursor.fetchall()
    
    # Create a notification for each user
    for user in users:
        user_id = user['id']
        notification_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO notifications
            (id, alert_id, user_id, `read`)
            VALUES (%s, %s, %s, FALSE)
        """, (notification_id, alert_id, user_id))
        
    current_app.logger.info(f"Created notifications for alert {alert_id} for {len(users)} users")

def send_alert_websocket_notification(alert_id, rule, host, value, message):
    """Send alert notifications via WebSocket."""
    try:
        from flask import current_app
        from app import socketio
        
        # Create notification payload
        notification_data = {
            'id': alert_id,
            'rule_id': rule['id'],
            'rule_name': rule['name'],
            'host': host,
            'value': value,
            'message': message,
            'comparison': rule['comparison'],
            'threshold': rule['threshold'],
            'metric_type': rule['metric_type'],
            'triggered_at': datetime.datetime.now().isoformat(),
            'status': 'triggered'
        }
        
        # Emit to all connected clients - they will filter based on their permissions
        socketio.emit('alert_notification', notification_data)
        
        current_app.logger.info(f"WebSocket notification sent for alert {alert_id}")
    except Exception as e:
        current_app.logger.error(f"Error sending WebSocket notification: {e}", exc_info=True)

def resolve_alert_if_needed(rule, host, current_value):
    """Resolve any active alerts that are no longer breaching threshold."""
    # Check if neither the main threshold nor email threshold (if configured) is breached
    is_main_breached = is_threshold_breached(rule, current_value)
    
    # For email threshold
    is_email_breached = False
    if rule.get('notifications', {}).get('email_enabled', False) and rule.get('email_threshold') is not None:
        is_email_breached = is_threshold_breached(rule, current_value, float(rule['email_threshold']))
    
    # Only resolve if both thresholds are no longer breached
    if not is_main_breached and not is_email_breached:
        db = get_db()
        cursor = db.cursor()
        
        # Find active alerts for this rule and host
        cursor.execute("""
            UPDATE alert_events 
            SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
            WHERE rule_id = %s AND host = %s AND status = 'triggered'
        """, (rule['id'], host))
        
        affected_rows = cursor.rowcount
        if affected_rows > 0:
            current_app.logger.info(f"Resolved {affected_rows} alerts for rule {rule['id']}, host {host}")
        
        db.commit()
        cursor.close()

def generate_alert_message(rule, host, value, is_email=False, is_sms=False):
    """Generate an alert message based on the rule and current value."""
    # Format the metric name (replace dots with spaces, ALL CAPS)
    metric_name = rule['metric_type'].replace('.', ' ').upper()
    
    # Get comparison symbol
    comparison_symbol = {
        'above': '>',
        'below': '<',
        'equal': '='
    }.get(rule['comparison'], '≠')
    
    # Format the value with appropriate units
    formatted_value = f"{value}%" if 'percent' in rule['metric_type'] else str(value)
    
    # For email alerts, use the email threshold
    if is_email and rule.get('email_threshold') is not None:
        threshold = rule['email_threshold']
    # For SMS alerts, use the SMS threshold
    elif is_sms and rule.get('sms_threshold') is not None:
        threshold = rule['sms_threshold']
    else:
        threshold = rule['threshold']
    
    # Format the threshold with the same units
    formatted_threshold = f"{threshold}%" if 'percent' in rule['metric_type'] else str(threshold)
    
    # Format the message with HTML formatting to match frontend
    message = f"{metric_name}: <strong>{formatted_value}</strong> {comparison_symbol} {formatted_threshold}"
    
    return message

def process_metric_for_alerts(measurement, host, fields, timestamp):
    """Process a single metric for alerts in real-time."""
    try:
        # Get all rules for this measurement
        rules = get_rules_for_measurement(measurement)
        
        for rule in rules:
            current_app.logger.info(f"Processing rule '{rule['name']}' (ID: {rule['id']}, enabled: {rule['enabled']})")
            
            # Double-check the rule is enabled
            if not rule.get('enabled', False):
                current_app.logger.info(f"Skipping disabled rule {rule['id']}")
                continue
                
            # Check if this rule applies to this host
            if not host_matches_rule(rule, host):
                current_app.logger.info(f"Rule {rule['id']} does not match host {host}")
                continue
            
            current_app.logger.info(f"Rule {rule['id']} applies to host {host}")
                
            # Extract the field we care about from the metric
            metric_parts = rule['metric_type'].split('.')
            if len(metric_parts) != 2 or metric_parts[0] != measurement:
                current_app.logger.info(f"Metric type mismatch: {rule['metric_type']} vs {measurement}")
                continue
                
            field_name = metric_parts[1]
            if field_name not in fields:
                current_app.logger.info(f"Field {field_name} not found in metric data: {list(fields.keys())}")
                continue
                
            current_value = fields[field_name]
            current_app.logger.info(f"Current value for {field_name}: {current_value}, threshold: {rule['threshold']}")
            
            # Record the value and update breach counts for all thresholds
            record_last_value(rule, host, current_value, timestamp)
            
            # Get current breach count and minimum required for main threshold
            breach_count = alert_state[rule['id']][host]['breach_count']
            min_breach_count = rule.get('breach_count')  # Default to 1 if not specified or zero
            
            current_app.logger.info(f"Threshold breached: {is_threshold_breached(rule, current_value)}, count: {breach_count}/{min_breach_count}")
            
            # Check if main threshold conditions are met for triggering an alert
            if is_threshold_breached(rule, current_value) and breach_count == min_breach_count:
                # Only trigger alert if we've reached minimum breach count
                current_app.logger.info(f"TRIGGERING ALERT for rule {rule['id']}, host {host}, value {current_value} after {breach_count} breaches")
                handle_alert_trigger(rule, host, current_value)
            
            # Check if email alert conditions are met (separate from main alert)
            if rule.get('notifications', {}).get('email_enabled', False) and rule.get('email_threshold') is not None:
                # Use a separate function to check if email alert conditions are met
                if is_email_alert_triggered(rule, host):
                    current_app.logger.info(f"TRIGGERING EMAIL ALERT for rule {rule['id']}, host {host}, value {current_value}")
                    # Handle as an email alert
                    handle_alert_trigger(rule, host, current_value, is_email_alert=True)

            # Check if SMS alert conditions are met
            if rule.get('notifications', {}).get('sms_enabled', False) and rule.get('sms_threshold') is not None:
                if is_sms_alert_triggered(rule, host):
                    current_app.logger.info(f"TRIGGERING SMS ALERT for rule {rule['id']}, host {host}, value {current_value}")
                    handle_alert_trigger(rule, host, current_value, is_sms_alert=True)
            
            # Resolve alerts if no thresholds are breached anymore
            resolve_alert_if_needed(rule, host, current_value)
    except Exception as e:
        current_app.logger.error(f"Error processing metric for alerts: {e}", exc_info=True)

def rebuild_alert_state():
    """Rebuild alert state from database on application startup."""
    global alert_state
    alert_state = {}
    current_app.logger.info("Alert state initialized")
