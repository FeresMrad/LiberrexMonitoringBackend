"""Alert detection and evaluation engine."""
import uuid
import time
from datetime import datetime
from flask import current_app
from app.mysql import get_db
from app.alerts.rules import get_all_rules, get_rules_for_measurement
from app.alerts.notification import send_alert_notification
from app.auth import get_all_hosts

# Global in-memory store for last seen values
# Format: {rule_id: {host: {'last_value': value, 'last_check': timestamp}}}
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

def is_threshold_breached(rule, value):
    """Check if a value breaches the threshold according to the comparison type."""
    comparison = rule['comparison']
    threshold = float(rule['threshold'])
    
    if comparison == 'above':
        return value > threshold
    elif comparison == 'below':
        return value < threshold
    elif comparison == 'equal':
        return value == threshold
    else:
        return False

def record_last_value(rule, host, value, timestamp):
    """Record the last value for a host/rule combination."""
    rule_id = rule['id']
    
    if rule_id not in alert_state:
        alert_state[rule_id] = {}
        
    if host not in alert_state[rule_id]:
        alert_state[rule_id][host] = {'last_value': None, 'last_check': None}
    
    # Update with new value
    alert_state[rule_id][host]['last_value'] = value
    alert_state[rule_id][host]['last_check'] = timestamp

def handle_alert_trigger(rule, host, value):
    """Handle the alert trigger by creating or updating an alert event."""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Check if there's already an active alert for this rule and host
    cursor.execute("""
        SELECT id, status FROM alert_events
        WHERE rule_id = %s AND host = %s AND status != 'resolved'
        ORDER BY triggered_at DESC LIMIT 1
    """, (rule['id'], host))
    
    existing_alert = cursor.fetchone()
    
    if existing_alert:
        # Alert already exists, don't create a new one
        current_app.logger.info(f"Alert already exists for rule {rule['id']}, host {host} - not creating duplicate")
        cursor.close()
        return
    
    # Create a new alert
    alert_id = str(uuid.uuid4())
    message = generate_alert_message(rule, host, value)
    
    try:
        current_app.logger.info(f"Inserting new alert with ID {alert_id} for rule {rule['id']}, host {host}")
        cursor.execute("""
            INSERT INTO alert_events
            (id, rule_id, host, status, value, message)
            VALUES (%s, %s, %s, 'triggered', %s, %s)
        """, (alert_id, rule['id'], host, value, message))
        
        db.commit()
        current_app.logger.info(f"Successfully inserted alert with ID {alert_id}")
    except Exception as e:
        current_app.logger.error(f"Database error inserting alert: {e}", exc_info=True)
        db.rollback()
    finally:
        cursor.close()
    
    # Send notification for the new alert
    try:
        send_alert_notification(rule, host, value, message)
    except Exception as e:
        current_app.logger.error(f"Error sending alert notification: {e}", exc_info=True)

def resolve_alert_if_needed(rule, host, current_value):
    """Resolve any active alerts that are no longer breaching threshold."""
    if not is_threshold_breached(rule, current_value):
        db = get_db()
        cursor = db.cursor()
        
        # Find active alerts for this rule and host
        cursor.execute("""
            UPDATE alert_events 
            SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
            WHERE rule_id = %s AND host = %s AND status != 'resolved'
        """, (rule['id'], host))
        
        db.commit()
        cursor.close()

def generate_alert_message(rule, host, value):
    """Generate an alert message based on the rule and current value."""
    metric_name = rule['metric_type'].replace('.', ' ').title()
    comparison_text = {
        'above': 'is above',
        'below': 'is below',
        'equal': 'equals'
    }.get(rule['comparison'], 'matches')
    
    return f"{metric_name} on {host} {comparison_text} threshold: {value} (threshold: {rule['threshold']})"

def process_metric_for_alerts(measurement, host, fields, timestamp):
    """Process a single metric for alerts in real-time."""
    try:
        # Get all enabled rules for this measurement
        rules = get_rules_for_measurement(measurement)
        current_app.logger.info(f"Processing {measurement} metric for {host}, found {len(rules)} rules")
        
        for rule in rules:
            current_app.logger.info(f"Checking rule '{rule['name']}' (ID: {rule['id']})")
            
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
            
            # Record the last value for this rule/host
            record_last_value(rule, host, current_value, timestamp)
            
            # Check if threshold is breached - SIMPLIFIED LOGIC
            is_breached = is_threshold_breached(rule, current_value)
            current_app.logger.info(f"Threshold breached: {is_breached}")
            
            if is_breached:
                # Immediately trigger alert if threshold is breached
                current_app.logger.info(f"TRIGGERING ALERT for rule {rule['id']}, host {host}, value {current_value}")
                handle_alert_trigger(rule, host, current_value)
            else:
                # Resolve any active alerts
                resolve_alert_if_needed(rule, host, current_value)
    except Exception as e:
        current_app.logger.error(f"Error processing metric for alerts: {e}", exc_info=True)

def clean_alert_state():
    """Clean up old alert state data."""
    current_time = time.time() * 1e9  # Convert to nanoseconds
    
    # Define maximum age for stored state (1 day)
    max_age_ns = 24 * 60 * 60 * 1e9
    cutoff_time = current_time - max_age_ns
    
    for rule_id in list(alert_state.keys()):
        for host in list(alert_state[rule_id].keys()):
            # If last check is older than cutoff, remove the entry
            last_check = alert_state[rule_id][host]['last_check']
            if last_check and last_check < cutoff_time:
                del alert_state[rule_id][host]
        
        # If rule has no hosts, remove it
        if not alert_state[rule_id]:
            del alert_state[rule_id]

def check_stale_metrics():
    """Check for and resolve alerts for metrics that have stopped reporting."""
    current_time = time.time() * 1e9  # Convert to nanoseconds
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Get all active alerts
    cursor.execute("""
        SELECT id, rule_id, host, triggered_at 
        FROM alert_events 
        WHERE status = 'triggered'
    """)
    
    active_alerts = cursor.fetchall()
    
    for alert in active_alerts:
        # If the alert is more than 30 minutes old, resolve it (metrics likely stopped reporting)
        alert_age_ns = current_time - (datetime.timestamp(alert['triggered_at']) * 1e9)
        stale_threshold_ns = 30 * 60 * 1e9  # 30 minutes in nanoseconds
        
        if alert_age_ns > stale_threshold_ns:
            # Resolve the alert
            cursor.execute("""
                UPDATE alert_events
                SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (alert['id'],))
    
    db.commit()
    cursor.close()

def rebuild_alert_state():
    """Rebuild alert state from database on application startup."""
    global alert_state
    alert_state = {}
