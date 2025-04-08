import psutil
import requests
import time
import subprocess
import json
import argparse

# InfluxDB 1.x details
url = "http://82.165.230.7:8086"
username = "liberrex"
password = "test"
database = "metrics"

# Parse command-line arguments
parser = argparse.ArgumentParser(description='System Monitoring Agent')
parser.add_argument('--host', 
                    required=True, 
                    help='Hostname for the monitoring agent')
args = parser.parse_args()

# Define the host name from command-line argument
host = args.host

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
        print(f"Raw 'who' output: {stdout_text}")  # Debug output
        
        sessions = []
        for line in stdout_text.splitlines():
            if not line.strip():
                continue
                
            print(f"Processing line: {line}")  # Debug output
            
            # Split the line into parts
            parts = line.split()
            print(f"Parts: {parts}")  # Debug output
            
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
                    
                    print(f"Found session: {session}")  # Debug output
                    sessions.append(session)
        
        print(f"Total sessions found: {len(sessions)}")  # Debug output
        return sessions
    except Exception as e:
        print(f"Error collecting SSH sessions: {e}")
        return []

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

    # Prepare points for InfluxDB 1.x line protocol
    points = [
        f"cpu,host={host} percent={cpu_percent}",
        f"memory,host={host} total={memory.total},available={memory.available},percent={memory.percent}",
        f"disk,host={host} total={disk.total},used={disk.used},percent={disk.percent}," +
        f"disk_read_per_second={disk_read_per_second},disk_write_per_second={disk_write_per_second}",
        f"network,host={host} sent_per_second={bytes_sent_per_second}," + 
        f"received_per_second={bytes_received_per_second},ip_adr=\"{local_ip}\"",
        f"uptime,host={host} uptime_seconds={uptime_seconds}",
        f"ssh_sessions,host={host} active_count={len(ssh_sessions)}," +
        f"sessions_json=\"{json.dumps(ssh_sessions).replace('\"', '\\"')}\""
    ]

    return points

def send_metrics():
    """Collect and send metrics to InfluxDB."""
    metrics = collect_metrics()
    try:
        # Prepare request parameters
        params = {
            'u': username,
            'p': password,
            'db': database
        }

        # Combine all points into a single payload
        payload = "\n".join(metrics)

        # Send metrics to InfluxDB
        response = requests.post(
            f"{url}/write",
            params=params,
            data=payload.encode('utf-8')
        )

        # Check response
        if response.status_code != 204:
            print(f"Error sending metrics: {response.text}")
        else:
            print(f"Metrics written successfully for host: {host}")

    except Exception as e:
        print(f"Error sending data to InfluxDB: {e}")

if __name__ == "__main__":
    print(f"Starting monitoring agent for host: {host}")
    while True:
        send_metrics()
        time.sleep(30)
