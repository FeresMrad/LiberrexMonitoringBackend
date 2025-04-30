"""Configuration settings for the monitoring agent."""
import os

# Agent ID configuration
AGENT_ID_FILE = "/opt/monitoring-agent/agent-id"

# InfluxDB 2.x details
INFLUXDB_URL = "http://82.165.230.7:8086"
INFLUXDB_TOKEN = "YnymHsvPMle5ppoGZKDLegZTHyypPtoJFW1sXRWdSH2paW-n24Io45vNObLHlfheaWDAT0e94OfMkRmOcRHmFw=="
INFLUXDB_ORG = "liberrex"
INFLUXDB_BUCKET = "metrics"

# Collection interval in seconds
COLLECTION_INTERVAL = 30

# Apache monitoring configuration
APACHE_STATUS_URL = "http://localhost/server-status?auto"
APACHE_ENABLED = True  # Set to False to disable Apache monitoring
APACHE_TIMEOUT = 5  # Timeout for Apache status request in seconds
