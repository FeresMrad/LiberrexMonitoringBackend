import psutil
import influxdb_client
import time
import subprocess
import json
import uuid
import os
import requests
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

# File to store the agent ID
AGENT_ID_FILE = "/opt/monitoring-agent/agent-id"

# InfluxDB 2.x details
url = "http://82.165.230.7:8086"
token = "YnymHsvPMle5ppoGZKDLegZTHyypPtoJFW1sXRWdSH2paW-n24Io45vNObLHlfheaWDAT0e94OfMkRmOcRHmFw=="
org = "liberrex"
bucket = "metrics"

# Apache monitoring configuration
APACHE_STATUS_URL = "http://localhost/server-status?auto"  # URL to Apache mod_status
APACHE_ENABLED = True  # Set to False to disable Apache monitoring
APACHE_TIMEOUT = 5  # Timeout for Apache status request in seconds

# Variables to store previous Apache metrics for interval calculations
last_apache_metrics = None
last_collection_time = None

# Try to get the agent ID from file, or generate a new one
def get_agent_id():
    # First check if the ID file exists
    if os.path.exists(AGENT_ID_FILE):
        try:
            with open(AGENT_ID_FILE, 'r') as f:
                agent_id = f.read().strip()
                if agent_id:
                    return agent_id
        except Exception as e:
            print(f"Error reading agent ID file: {e}")
    
    # If we got here, either the file doesn't exist or is empty/corrupted
    # Generate a new agent ID
    agent_id = str(uuid.uuid4())
    
    # Try to save it to the file
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(AGENT_ID_FILE), exist_ok=True)
        
        with open(AGENT_ID_FILE, 'w') as f:
            f.write(agent_id)
    except Exception as e:
        print(f"Error saving agent ID file: {e}")
    
    return agent_id

# Get the agent ID - this will either retrieve existing or generate new
host = get_agent_id()
print(f"Using agent ID: {host}")

# Initialize InfluxDB client
client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

# Variables to store previous net_io values
previous_net_io = psutil.net_io_counters()
previous_disk_io = psutil.disk_io_counters()

def get_local_ip_from_interfaces():
    """Retrieve the local IP from network interfaces."""
    for interface, addresses in psutil.net_if_addrs().items():
        for addr in addresses:
            if addr.family == 2 and not addr.address.startswith("127."):  # IPv4 and not loopback
                return addr.address
    return "Unknown"

def collect_ssh_sessions():
    """Collect active SSH sessions"""
    try:
        # Run the 'who' command to get active sessions
        process = subprocess.Popen(['who'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()

        if stderr:
            print(f"Error getting SSH sessions: {stderr.decode('utf-8')}")
            return []

        stdout_text = stdout.decode('utf-8')

        sessions = []
        for line in stdout_text.splitlines():
            if not line.strip():
                continue

            # Split the line into parts
            parts = line.split()

            # The 'who' command output format might vary, we need to be more flexible
            if len(parts) >= 3:  # At minimum we need username, tty, and time
                username = parts[0]
                tty = parts[1]

                # If it contains 'pts', it's likely an SSH session
                # Check different indices for IP address (depends on output format)
                remote_addr = None
                for part in parts:
                    if '(' in part and ')' in part:
                        remote_addr = part.strip('()')
                        break

                if 'pts' in tty and remote_addr:
                    login_time_parts = []
                    for i in range(2, len(parts)):
                        if '(' not in parts[i]:
                            login_time_parts.append(parts[i])
                        else:
                            break

                    login_time = ' '.join(login_time_parts)

                    session = {
                        'user': username,
                        'tty': tty,
                        'from': remote_addr,
                        'login_time': login_time
                    }

                    sessions.append(session)

        return sessions
    except Exception as e:
        print(f"Error collecting SSH sessions: {e}")
        return []

def collect_apache_metrics():
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

def collect_metrics():
    """Collect system metrics."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    disk_io = psutil.disk_io_counters()
    global previous_net_io, previous_disk_io
    net_io = psutil.net_io_counters()
    uptime_seconds = time.time() - psutil.boot_time()

    bytes_sent_per_second = (net_io.bytes_sent - previous_net_io.bytes_sent) / 30
    bytes_received_per_second = (net_io.bytes_recv - previous_net_io.bytes_recv) / 30

    disk_read_per_second = (disk_io.read_bytes - previous_disk_io.read_bytes) / 30
    disk_write_per_second = (disk_io.write_bytes - previous_disk_io.write_bytes) / 30

    previous_net_io = net_io
    previous_disk_io = disk_io

    local_ip = get_local_ip_from_interfaces()

    # Collect SSH sessions
    ssh_sessions = collect_ssh_sessions()

    points = [
        Point("cpu").tag("host", host).field("percent", cpu_percent),
        Point("memory").tag("host", host).field("total", memory.total).field("available", memory.available).field("percent", memory.percent),
        Point("disk").tag("host", host).field("total", disk.total).field("used", disk.used).field("percent", disk.percent)
        .field("disk_read_per_second", disk_read_per_second).field("disk_write_per_second", disk_write_per_second),
        Point("network").tag("host", host).field("sent_per_second", bytes_sent_per_second).field("received_per_second", bytes_received_per_second).field("ip_adr", local_ip),
        Point("uptime").tag("host", host).field("uptime_seconds", uptime_seconds)
    ]

    # Always send the SSH sessions point, even if empty
    ssh_point = Point("ssh_sessions").tag("host", host)
    ssh_point.field("active_count", len(ssh_sessions))
    ssh_point.field("sessions_json", json.dumps(ssh_sessions))
    points.append(ssh_point)
    
    # Collect Apache metrics
    apache_points = collect_apache_metrics()
    points.extend(apache_points)

    return points

def send_metrics():
    """Collect and send metrics to InfluxDB."""
    metrics = collect_metrics()
    try:
        write_api.write(bucket=bucket, org=org, record=metrics)
        print("Metrics written successfully.")
    except Exception as e:
        print(f"Error sending data to InfluxDB: {e}")

while True:
    send_metrics()
    time.sleep(30)
