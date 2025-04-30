"""Collectors package for the monitoring agent."""
from . import system
from . import ssh
from . import apache

def initialize():
    """Initialize all collectors."""
    system.initialize()

def collect_all(host):
    """Collect metrics from all collectors."""
    metrics = []
    
    # System metrics
    metrics.extend(system.collect_all(host))
    
    # SSH metrics
    metrics.extend(ssh.collect(host))
    
    # Apache metrics
    metrics.extend(apache.collect(host))
    
    return metrics
