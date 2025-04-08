#!/bin/bash

# Check if script is run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

# Check if hostname is provided
if [ $# -eq 0 ]; then
    echo "Error: Hostname must be specified"
    echo "Usage: $0 <hostname>"
    exit 1
fi

# Get the hostname from the first argument
HOST=$1

# Update package lists
apt update

# Install prerequisites
apt install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential

# Create a virtual environment
python3 -m venv /opt/monitoring-agent/venv

# Activate virtual environment and install Python packages
/opt/monitoring-agent/venv/bin/pip install psutil requests influxdb-client

# Create directory for monitoring agent
mkdir -p /opt/monitoring-agent

# Copy agent script
cp agent.py /opt/monitoring-agent/agent.py

# Create systemd service file
cat > /etc/systemd/system/monitoring-agent.service << EOL
[Unit]
Description=System Monitoring Agent
After=network.target

[Service]
ExecStart=/opt/monitoring-agent/venv/bin/python /opt/monitoring-agent/agent.py --host $HOST
WorkingDirectory=/opt/monitoring-agent
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Reload systemd to recognize the new service
systemctl daemon-reload

# Enable the service to start on boot
systemctl enable monitoring-agent

# Start the service
systemctl start monitoring-agent

echo "Monitoring agent installed and started successfully for host: $HOST"
