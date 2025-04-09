import psutil
import influxdb_client
import time
import subprocess
import json
import argparse
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

# InfluxDB 2.x details
url = "http://82.165.230.7:8086"  # Update with your InfluxDB 2.x URL if necessary
token = "YnymHsvPMle5ppoGZKDLegZTHyypPtoJFW1sXRWdSH2paW-n24Io45vNObLHlfheaWDAT0e94OfMkRmOcRHmFw=="
org = "liberrex"
bucket = "metrics"

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Monitoring Agent")
parser.add_argument("--host", required=True, help="Hostname to tag metrics with")
args = parser.parse_args()
host = args.host


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
        #print(f"Raw 'who' output: {stdout_text}")  # Debug output

        sessions = []
        for line in stdout_text.splitlines():
            if not line.strip():
                continue

            #print(f"Processing line: {line}")  # Debug output

            # Split the line into parts
            parts = line.split()
            #print(f"Parts: {parts}")  # Debug output

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

                    #print(f"Found session: {session}")  # Debug output
                    sessions.append(session)

        #print(f"Total sessions found: {len(sessions)}")  # Debug output
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

    points = [
        Point("cpu").tag("host", host).field("percent", cpu_percent),
        Point("memory").tag("host", host).field("total", memory.total).field("available", memory.available).field("percent", memory.percent),
        Point("disk").tag("host", host).field("total", disk.total).field("used", disk.used).field("percent", disk.percent)
        .field("disk_read_per_second", disk_read_per_second).field("disk_write_per_second", disk_write_per_second),
        Point("network").tag("host", host).field("sent_per_second", bytes_sent_per_second).field("received_per_second", bytes_received_per_second).field("ip_adr", local_ip),
        Point("uptime").tag("host", host).field("uptime_seconds", uptime_seconds)
    ]

    # Add SSH sessions point if there are any sessions
    # Always send the SSH sessions point, even if empty
    ssh_point = Point("ssh_sessions").tag("host", host)
    ssh_point.field("active_count", len(ssh_sessions))
    ssh_point.field("sessions_json", json.dumps(ssh_sessions))
    points.append(ssh_point)

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
