"""System metrics collector for CPU, memory, disk, network, and uptime."""
import psutil
import time
from influxdb_client import Point

# Store previous metrics for rate calculations
previous_net_io = None 
previous_disk_io = None

def initialize():
    """Initialize collector state."""
    global previous_net_io, previous_disk_io
    previous_net_io = psutil.net_io_counters()
    previous_disk_io = psutil.disk_io_counters()

def get_local_ip_from_interfaces():
    """Retrieve the local IP from network interfaces."""
    for interface, addresses in psutil.net_if_addrs().items():
        for addr in addresses:
            if addr.family == 2 and not addr.address.startswith("127."):  # IPv4 and not loopback
                return addr.address
    return "Unknown"

def collect_cpu_metrics(host):
    """Collect CPU usage metrics."""
    cpu_percent = psutil.cpu_percent(interval=1)
    return Point("cpu").tag("host", host).field("percent", cpu_percent)

def collect_memory_metrics(host):
    """Collect memory usage metrics."""
    memory = psutil.virtual_memory()
    return Point("memory").tag("host", host)\
        .field("total", memory.total)\
        .field("available", memory.available)\
        .field("percent", memory.percent)

def collect_disk_metrics(host):
    """Collect disk usage and I/O metrics."""
    global previous_disk_io
    
    # Get current values
    disk = psutil.disk_usage('/')
    disk_io = psutil.disk_io_counters()
    
    # Calculate rates (per second)
    disk_read_per_second = (disk_io.read_bytes - previous_disk_io.read_bytes) / 30
    disk_write_per_second = (disk_io.write_bytes - previous_disk_io.write_bytes) / 30
    
    # Store current values for next calculation
    previous_disk_io = disk_io
    
    return Point("disk").tag("host", host)\
        .field("total", disk.total)\
        .field("used", disk.used)\
        .field("percent", disk.percent)\
        .field("disk_read_per_second", disk_read_per_second)\
        .field("disk_write_per_second", disk_write_per_second)

def collect_network_metrics(host):
    """Collect network metrics including IP and traffic rates."""
    global previous_net_io
    
    # Get current values
    net_io = psutil.net_io_counters()
    
    # Calculate rates (per second)
    bytes_sent_per_second = (net_io.bytes_sent - previous_net_io.bytes_sent) / 30
    bytes_received_per_second = (net_io.bytes_recv - previous_net_io.bytes_recv) / 30
    
    # Store current values for next calculation
    previous_net_io = net_io
    
    # Get local IP address
    local_ip = get_local_ip_from_interfaces()
    
    return Point("network").tag("host", host)\
        .field("sent_per_second", bytes_sent_per_second)\
        .field("received_per_second", bytes_received_per_second)\
        .field("ip_adr", local_ip)

def collect_uptime_metrics(host):
    """Collect system uptime metrics."""
    uptime_seconds = time.time() - psutil.boot_time()
    return Point("uptime").tag("host", host).field("uptime_seconds", uptime_seconds)

def collect_all(host):
    """Collect all system metrics."""
    metrics = [
        collect_cpu_metrics(host),
        collect_memory_metrics(host),
        collect_disk_metrics(host),
        collect_network_metrics(host),
        collect_uptime_metrics(host)
    ]
    return metrics
