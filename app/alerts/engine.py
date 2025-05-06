"""Alert detection and evaluation engine."""
import uuid
import time
from datetime import datetime
from flask import current_app
from app.mysql import get_db
from app.alerts.rules import get_all_rules, get_rules_for_measurement
from app.alerts.notification import send_alert_notification
from app.auth import get_all_hosts

# Global in-memory store for breach history
# Format: {rule_id: {host: {'breaches': [(timestamp, value)], 'last_check': timestamp}}}
breach_history = {}

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

def record_breach(rule, host, value, timestamp):
    """Record a threshold breach for duration tracking."""
    rule_id = rule['id']
    
    if rule_id not in breach_history:
        breach_history[rule_id] = {}
        
    if host not in breach_history[rule_id]:
        breach_history[rule_id][host] = {'breaches': [], 'last_check': None}
    
    # Convert timestamp to integer if it's a string
    if isinstance(timestamp, str):
        timestamp = int(timestamp)
    
    # Add new breach
    breach_history[rule_id][host]['breaches'].append((timestamp, value))
    breach_history[rule_id][host]['last_check'] = timestamp
    
    # Remove old breaches (outside duration window)
    duration_ns = rule['duration_minutes'] * 60 * 1000000000  # Convert to nanoseconds
    cutoff = timestamp - duration_ns
    
    breach_history[rule_id][host]['breaches'] = [
        b for b in breach_history[rule_id][host]['breaches'] if b[0] >= cutoff
    ]

def clear_breach_history(rule, host):
    """Clear breach history when conditions return to normal."""
    rule_id = rule['id']
    
    if rule_id in breach_history and host in breach_history[rule_id]:
        breach_history[rule_id][host]['breaches'] = []

def check_duration_from_history(rule, host):
    """Check if breaches have persisted for the required duration."""
    rule_id = rule['id']
    
    if rule_id not in breach_history or host not in breach_history[rule_id]:
        current_app.logger.info(f"No breach history for rule {rule_id}, host {host}")
        return False
    
    breaches = breach_history[rule_id][host]['breaches']
    
    if not breaches:
        current_app.logger.info(f"Empty breach history for rule {rule_id}, host {host}")
        return False
    
    # Need at least 3 data points to consider it persistent
    if len(breaches) < 2:
        current_app.logger.info(f"Only {len(breaches)} breach points for rule {rule_id}, host {host} - need at least 3")
        return False
    
    # Get oldest and newest breach timestamps
    oldest = min(breaches, key=lambda x: x[0])[0]
    newest = max(breaches, key=lambda x: x[0])[0]
    
    # Calculate duration in nanoseconds
    duration_ns = newest - oldest
    required_duration_ns = rule['duration_minutes'] * 60 * 1000000000
    
    # Calculate percentage of required duration
    percentage = (duration_ns / required_duration_ns) * 100
    current_app.logger.info(f"Duration: {duration_ns/1e9:.2f}s / {required_duration_ns/1e9:.2f}s ({percentage:.1f}%)")
    
    # Need at least 70% of the required duration with breaches
    is_long_enough = duration_ns >= (required_duration_ns * 0.7)
    current_app.logger.info(f"Duration check result: {is_long_enough}")
    return is_long_enough

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
            
            # Check if threshold is breached
            is_breached = is_threshold_breached(rule, current_value)
            current_app.logger.info(f"Threshold breached: {is_breached}")
            
            if is_breached:
                # Add to breach history
                record_breach(rule, host, current_value, timestamp)
                
                # Check breach history after recording
                rule_id = rule['id']
                if rule_id in breach_history and host in breach_history[rule_id]:
                    breach_count = len(breach_history[rule_id][host]['breaches'])
                    current_app.logger.info(f"Breach history: {breach_count} breaches recorded for rule {rule_id}, host {host}")
                
                # Check if conditions for duration are met
                duration_met = check_duration_from_history(rule, host)
                current_app.logger.info(f"Duration conditions met: {duration_met}")
                
                if duration_met:
                    # Trigger alert
                    current_app.logger.info(f"TRIGGERING ALERT for rule {rule['id']}, host {host}, value {current_value}")
                    handle_alert_trigger(rule, host, current_value)
            else:
                # Clear breach history
                clear_breach_history(rule, host)
                
                # Resolve any active alerts
                resolve_alert_if_needed(rule, host, current_value)
    except Exception as e:
        current_app.logger.error(f"Error processing metric for alerts: {e}", exc_info=True)

def clean_breach_history():
    """Clean up old breach history data."""
    current_time = time.time() * 1e9  # Convert to nanoseconds
    
    # Get all rules to determine proper duration windows
    rules = get_all_rules()
    for rule in rules:
        rule_id = rule['id']
        if rule_id not in breach_history:
            continue
            
        # Convert duration to nanoseconds + 30 minutes buffer
        duration_ns = (rule['duration_minutes'] + 30) * 60 * 1000000000
        cutoff = current_time - duration_ns
        
        for host in list(breach_history[rule_id].keys()):
            # Remove old breaches
            breach_history[rule_id][host]['breaches'] = [
                b for b in breach_history[rule_id][host]['breaches'] if b[0] >= cutoff
            ]
            
            # If host has no breaches and last check is old, remove it
            if not breach_history[rule_id][host]['breaches'] and \
               breach_history[rule_id][host]['last_check'] < cutoff:
                del breach_history[rule_id][host]
        
        # If rule has no hosts, remove it
        if not breach_history[rule_id]:
            del breach_history[rule_id]

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
        # If the alert is more than 30 minutes old and no new breaches
        # have been recorded, resolve it (metrics likely stopped reporting)
        alert_age_ns = current_time - (datetime.timestamp(alert['triggered_at']) * 1e9)
        stale_threshold_ns = 30 * 60 * 1e9  # 30 minutes in nanoseconds
        
        if alert_age_ns > stale_threshold_ns:
            rule_id = alert['rule_id']
            host = alert['host']
            
            # Check if we have recent breach history
            has_recent_breaches = False
            if (rule_id in breach_history and 
                host in breach_history[rule_id] and 
                breach_history[rule_id][host]['breaches']):
                
                newest_breach = max(breach_history[rule_id][host]['breaches'], 
                                   key=lambda x: x[0])
                breach_age_ns = current_time - newest_breach[0]
                
                if breach_age_ns < stale_threshold_ns:
                    has_recent_breaches = True
            
            # If no recent breaches, resolve the alert
            if not has_recent_breaches:
                cursor.execute("""
                    UPDATE alert_events
                    SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (alert['id'],))
    
    db.commit()
    cursor.close()

def rebuild_alert_state():
    """Rebuild alert state from database on application startup."""
    global breach_history
    breach_history = {}
