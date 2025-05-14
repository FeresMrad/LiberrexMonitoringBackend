"""Rule-based uptime checker module for monitoring host activity."""
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
from flask import current_app

# Global scheduler reference
scheduler = None
job = None
flask_app = None  # Store the Flask app reference globally

def init_uptime_checker(app):
    """Initialize the uptime checker scheduler."""
    global scheduler, job, flask_app
    
    # Store the Flask app reference
    flask_app = app
    
    # Create scheduler if it doesn't exist
    if scheduler is None:
        scheduler = BackgroundScheduler()
        scheduler.start()
        
        # Register shutdown on app exit
        atexit.register(scheduler.shutdown)
    
    def check_hosts_uptime():
        """Check hosts' uptime based on active rules."""
        # Use the stored app reference to create a context
        with flask_app.app_context():
            try:
                from app.services.influxdb import query_influxdb
                from app.alerts.rules import get_all_rules
                from app.alerts.engine import alert_state, handle_alert_trigger, is_threshold_breached, resolve_alert_if_needed
                
                # Get all active uptime rules
                all_rules = get_all_rules()
                uptime_rules = [
                    rule for rule in all_rules
                    if rule.get('enabled', False) 
                    and rule.get('metric_type', '') == 'uptime.status'
                ]
                
                # If no uptime rules, don't do anything
                if not uptime_rules:
                    print("No active uptime rules, skipping check")
                    return
                
                # Collect all unique hosts from all uptime rules
                hosts_to_check = set()
                for rule in uptime_rules:
                    for target in rule.get('targets', []):
                        if target.get('target_type') == 'all':
                            # For 'all' targets, we need to get all hosts
                            hosts_query = 'SHOW TAG VALUES FROM "uptime" WITH KEY = "host"'
                            hosts_response = query_influxdb(hosts_query)
                            
                            if hosts_response["results"][0].get("series"):
                                for host in hosts_response["results"][0]["series"][0]["values"]:
                                    hosts_to_check.add(host[1])
                        
                        elif target.get('target_type') == 'host':
                            # Add specific host
                            hosts_to_check.add(target.get('target_id'))
                
                # Current time in UTC
                current_time = datetime.datetime.now(datetime.timezone.utc)
                
                # Check each host's uptime
                for host in hosts_to_check:
                    try:
                        # Query to get the latest uptime for this host
                        uptime_query = f'SELECT "uptime_seconds" FROM "uptime" WHERE "host" = \'{host}\' ORDER BY time DESC LIMIT 1'
                        uptime_response = query_influxdb(uptime_query)
                        
                        if uptime_response["results"][0].get("series"):
                            values = uptime_response["results"][0]["series"][0]["values"][0]
                            timestamp_str = values[0]
                            
                            # Convert the timestamp to a datetime object
                            last_timestamp = datetime.datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            
                            # Calculate difference in seconds
                            diff_seconds = (current_time - last_timestamp).total_seconds()
                            
                            # Process each uptime rule for this host
                            for rule in uptime_rules:
                                # Skip rules that don't apply to this host
                                if not host_matches_rule(rule, host):
                                    continue
                                
                                rule_id = rule['id']
                                threshold = rule.get('threshold', 60)  # Default to 60 seconds
                                
                                # Initialize state tracking for this rule and host if needed
                                if rule_id not in alert_state:
                                    alert_state[rule_id] = {}
                                if host not in alert_state[rule_id]:
                                    alert_state[rule_id][host] = {
                                        'last_value': None,
                                        'last_check': None,
                                        'breach_count': 0,
                                        'email_breach_count': 0,
                                        'sms_breach_count': 0
                                    }
                                
                                # Get the minimum breach count needed for alerting
                                min_breach_count = rule.get('breach_count', 1)
                                
                                # Previous breach count for checking transitions
                                previous_breach_count = alert_state[rule_id][host]['breach_count']
                                    
                                # Check if host appears to be down
                                is_down = diff_seconds > threshold
                                if is_down:
                                    # Increment breach count
                                    alert_state[rule_id][host]['breach_count'] += 1
                                    current_breach_count = alert_state[rule_id][host]['breach_count']
                                    
                                    # Log appropriate message based on breach count
                                    if current_breach_count >= min_breach_count:
                                        print(f"WARNING: Host {host} appears to be down - last uptime was {diff_seconds:.2f} seconds ago (breach count: {current_breach_count}/{min_breach_count})")
                                    else:
                                        print(f"MONITORING: Host {host} possible downtime - last uptime was {diff_seconds:.2f} seconds ago (breach count: {current_breach_count}/{min_breach_count})")
                                    
                                    # Create alert if breach count has just reached the threshold
                                    if current_breach_count == min_breach_count:
                                        print(f"TRIGGERING ALERT for rule {rule['id']}, host {host}, value {diff_seconds} after {current_breach_count} breaches")
                                        # Create an alert in the database
                                        handle_alert_trigger(rule, host, diff_seconds)
                                else:
                                    # If host was previously breaching threshold, log recovery
                                    if previous_breach_count > 0:
                                        print(f"RECOVERY: Host {host} is back up after {previous_breach_count} breach checks")
                                        
                                        # If breach count had reached threshold, resolve the alert
                                        if previous_breach_count >= min_breach_count:
                                            resolve_alert_if_needed(rule, host, diff_seconds)
                                        
                                    # Reset breach count since host is up
                                    alert_state[rule_id][host]['breach_count'] = 0
                                
                                # Update last values
                                alert_state[rule_id][host]['last_value'] = diff_seconds
                                alert_state[rule_id][host]['last_check'] = timestamp_str
                        else:
                            print(f"WARNING: No uptime data found for host {host}")
                    
                    except Exception as e:
                        print(f"ERROR: Error checking uptime for host {host}: {e}")
            
            except Exception as e:
                print(f"ERROR in uptime checker: {e}")
    
    # Helper function to check if a host is targeted by a rule
    def host_matches_rule(rule, host):
        """Check if a host is targeted by this rule."""
        # Check each target in the rule
        for target in rule.get('targets', []):
            if target['target_type'] == 'all':
                return True
            elif target['target_type'] == 'host' and target['target_id'] == host:
                return True
        return False
    
    # Remove existing job if it exists
    if job is not None:
        scheduler.remove_job(job.id)
    
    # Schedule the uptime checker to run every 30 seconds
    job = scheduler.add_job(check_hosts_uptime, 'interval', seconds=30)
    
    return scheduler

def update_uptime_checker(app):
    """Update the uptime checker when rules change."""
    # Simply re-initialize to pick up new rules
    init_uptime_checker(app)
