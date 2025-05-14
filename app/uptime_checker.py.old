"""Rule-based uptime checker module for monitoring host activity."""
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# Global scheduler reference
scheduler = None
job = None

def init_uptime_checker(app):
    """Initialize the uptime checker scheduler."""
    global scheduler, job
    
    # Create scheduler if it doesn't exist
    if scheduler is None:
        scheduler = BackgroundScheduler()
        scheduler.start()
        
        # Register shutdown on app exit
        atexit.register(scheduler.shutdown)
    
    def check_hosts_uptime():
        """Check hosts' uptime based on active rules."""
        with app.app_context():
            from app.services.influxdb import query_influxdb
            from app.alerts.rules import get_all_rules
            
            # Get all active uptime rules
            all_rules = get_all_rules()
            uptime_rules = [
                rule for rule in all_rules
                if rule.get('enabled', False) 
                and rule.get('metric_type', '').startswith('uptime.')
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
                        
                        # If difference is more than 60 seconds, log it
                        if diff_seconds > 60:
                            print(f"WARNING: Host {host} appears to be down - last uptime was {diff_seconds:.2f} seconds ago")
                        else:
                            print(f"INFO: Host {host} is up - last check was {diff_seconds:.2f} seconds ago")
                    else:
                        print(f"WARNING: No uptime data found for host {host}")
                
                except Exception as e:
                    print(f"ERROR: Error checking uptime for host {host}: {e}")
    
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
