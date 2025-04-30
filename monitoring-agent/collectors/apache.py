"""Apache metrics collector."""
import requests
import time
from influxdb_client import Point
from config import APACHE_STATUS_URL, APACHE_ENABLED, APACHE_TIMEOUT

# Variables to store previous Apache metrics for interval calculations
last_apache_metrics = None
last_collection_time = None

def collect_apache_metrics(host):
    """Collect Apache metrics from server-status?auto endpoint."""
    global last_apache_metrics, last_collection_time
    apache_points = []
    
    if not APACHE_ENABLED:
        return []
    
    current_time = time.time()
    
    try:
        # Request the server-status page
        response = requests.get(APACHE_STATUS_URL, timeout=APACHE_TIMEOUT)
        response.raise_for_status()
        
        # Parse the response line by line
        current_metrics = {}
        for line in response.text.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                current_metrics[key.strip()] = value.strip()
        
        # Add raw metrics from Apache
        apache_points.append(
            Point("apache_raw").tag("host", host)
                .field("uptime_seconds", int(current_metrics.get("Uptime", 0)))
                .field("total_accesses", int(current_metrics.get("Total Accesses", 0)))
                .field("total_kbytes", int(current_metrics.get("Total kBytes", 0)))
                .field("req_per_sec", float(current_metrics.get("ReqPerSec", 0)))
                .field("bytes_per_req", float(current_metrics.get("BytesPerReq", 0)))
                .field("bytes_per_sec", float(current_metrics.get("BytesPerSec", 0)))
                .field("duration_per_req", float(current_metrics.get("DurationPerReq", 0)))
                .field("busy_workers", int(current_metrics.get("BusyWorkers", 0)))
                .field("idle_workers", int(current_metrics.get("IdleWorkers", 0)))
                .field("conns_total", int(current_metrics.get("ConnsTotal", 0)))
        )
        
        # Health check metric
        apache_points.append(
            Point("apache_health").tag("host", host)
                .field("is_responsive", 1)  # 1 = healthy
        )
        
        # Calculate interval-based metrics if we have previous values
        if last_apache_metrics and last_collection_time:
            time_delta = current_time - last_collection_time
            
            # Calculate deltas
            accesses_delta = int(current_metrics.get("Total Accesses", 0)) - int(last_apache_metrics.get("Total Accesses", 0))
            kbytes_delta = int(current_metrics.get("Total kBytes", 0)) - int(last_apache_metrics.get("Total kBytes", 0))
            duration_delta = float(current_metrics.get("Total Duration", 0) or 0) - float(last_apache_metrics.get("Total Duration", 0) or 0)
            
            # Only add interval metrics if there's been some activity
            if time_delta > 0:
                interval_req_per_sec = accesses_delta / time_delta
                interval_bytes_per_sec = kbytes_delta * 1024 / time_delta
                
                # Avoid division by zero
                interval_bytes_per_req = 0
                interval_duration_per_req = 0
                
                if accesses_delta > 0:
                    interval_bytes_per_req = kbytes_delta * 1024 / accesses_delta
                    interval_duration_per_req = duration_delta / accesses_delta
                
                apache_points.append(
                    Point("apache_interval").tag("host", host)
                        .field("interval_req_per_sec", interval_req_per_sec)
                        .field("interval_bytes_per_sec", interval_bytes_per_sec)
                        .field("interval_bytes_per_req", interval_bytes_per_req)
                        .field("interval_duration_per_req", interval_duration_per_req)
                        .field("accesses_delta", accesses_delta)
                )
        
        # Update stored values for next run
        last_apache_metrics = current_metrics
        last_collection_time = current_time
        
    except requests.exceptions.ConnectionError:
        print("Cannot connect to Apache server-status. Is Apache running?")
        # Add health check metric indicating Apache is not responsive
        apache_points.append(
            Point("apache_health").tag("host", host)
                .field("is_responsive", 0)  # 0 = not responding
        )
    except requests.exceptions.RequestException as e:
        print(f"Error requesting Apache status: {e}")
        apache_points.append(
            Point("apache_health").tag("host", host)
                .field("is_responsive", 0)
        )
    except Exception as e:
        print(f"Error collecting Apache metrics: {e}")
    
    return apache_points

def collect(host):
    """Collect Apache metrics for the host."""
    return collect_apache_metrics(host)
