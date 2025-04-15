#!/bin/bash

# Check if script is run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

# Update package lists
apt update

# Install prerequisites
apt install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential

# Create the agent directory
mkdir -p /opt/monitoring-agent

# Create a virtual environment
python3 -m venv /opt/monitoring-agent/venv

# Activate virtual environment and install Python packages
/opt/monitoring-agent/venv/bin/pip install psutil requests influxdb-client uuid

# Copy agent script
cp agent.py /opt/monitoring-agent/agent.py

# Generate or read agent-id for rsyslog configuration
AGENT_ID_FILE="/opt/monitoring-agent/agent-id"
if [ -f "$AGENT_ID_FILE" ]; then
    AGENT_ID=$(cat "$AGENT_ID_FILE")
    echo "Using existing agent-id: $AGENT_ID"
else
    # Generate a new UUID
    AGENT_ID=$(python3 -c 'import uuid; print(str(uuid.uuid4()))')
    echo "$AGENT_ID" > "$AGENT_ID_FILE"
    echo "Generated new agent-id: $AGENT_ID"
fi

# Create systemd service file
cat > /etc/systemd/system/monitoring-agent.service << EOL
[Unit]
Description=System Monitoring Agent
After=network.target

[Service]
ExecStart=/opt/monitoring-agent/venv/bin/python /opt/monitoring-agent/agent.py
WorkingDirectory=/opt/monitoring-agent
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Add configuration to rsyslog if not already present
echo "# Checking and configuring rsyslog for remote logging"

# Remove any existing LocalHostName lines
if grep -q "^\$LocalHostName" /etc/rsyslog.conf; then
    # Use sed to remove any existing LocalHostName lines
    sed -i '/^\$LocalHostName/d' /etc/rsyslog.conf
    echo "Removed existing LocalHostName configuration"
fi

# Now add the new LocalHostName line
echo "\$LocalHostName $AGENT_ID" >> /etc/rsyslog.conf
echo "Added LocalHostName configuration to rsyslog"

# Check if forwarding rule exists
if ! grep -q "^\*\.\*  @@82\.165\.230\.7:29514" /etc/rsyslog.conf; then
    echo "*.*  @@82.165.230.7:29514" >> /etc/rsyslog.conf
    echo "Added remote logging configuration to rsyslog"
else
    echo "Remote logging already configured in rsyslog"
fi

# Restart rsyslog service only if changes were made
if grep -q "^\$LocalHostName $AGENT_ID" /etc/rsyslog.conf && grep -q "^\*\.\*  @@82\.165\.230\.7:29514" /etc/rsyslog.conf; then
    systemctl restart rsyslog
    echo "Rsyslog configured and restarted for remote logging"
fi

# Reload systemd to recognize the new service
systemctl daemon-reload

# Enable the service to start on boot
systemctl enable monitoring-agent

# Start the service
systemctl start monitoring-agent

echo "Monitoring agent installed and started successfully with agent ID: $AGENT_ID"
