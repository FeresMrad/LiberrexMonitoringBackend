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

# Create the agent directory and subdirectories
mkdir -p /opt/monitoring-agent/collectors

# Create a virtual environment
python3 -m venv /opt/monitoring-agent/venv

# Activate virtual environment and install Python packages
/opt/monitoring-agent/venv/bin/pip install psutil requests influxdb-client uuid

# Copy agent files
echo "Copying agent files..."
cp agent.py config.py agent_id.py /opt/monitoring-agent/
cp collectors/__init__.py collectors/system.py collectors/ssh.py collectors/apache.py /opt/monitoring-agent/collectors/

# Create empty __init__.py if not copied
touch /opt/monitoring-agent/collectors/__init__.py

# Set correct permissions
chmod 755 /opt/monitoring-agent/agent.py

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

# Create Apache logging configuration for rsyslog
echo "# Setting up Apache access log monitoring with rsyslog"
cat > /etc/rsyslog.d/apache.conf << EOL
###############################################################################
# 1) Load the imfile module
###############################################################################
module(load="imfile" PollingInterval="10")
###############################################################################
# 2) Watch Apache's access.log
###############################################################################
input(type="imfile"
      File="/var/log/apache2/*access.log"    # the file to tail
      Tag="apache-access:"                   # prefix you'll see in \$programname
      Facility="local6"                      # keep it separate
      Severity="info"
      PersistStateInterval="200"
)
# Filter out server-status requests from 127.0.0.1
if (\$programname == 'apache-access' and
    \$msg contains '127.0.0.1' and
    \$msg contains 'GET /server-status?auto') then {
    stop  # drop the message, don't log or forward it
}
EOL
echo "Created Apache rsyslog configuration file"

# Modify Apache logging format to include response time (%D) if Apache is installed
if [ -f "/etc/apache2/apache2.conf" ]; then
    echo "# Modifying Apache logging format to include response time (%D)"
    
    # Check if LogFormat lines already include %D
    # If not, update them
    APACHE_MODIFIED=0
    
    # Update vhost_combined format
    if grep -q 'LogFormat "%v:%p %h %l %u %t \\"%r\\" %>s %O \\"%{Referer}i\\" \\"%{User-Agent}i\\"" vhost_combined' /etc/apache2/apache2.conf; then
        sed -i 's/LogFormat "%v:%p %h %l %u %t \\"%r\\" %>s %O \\"%{Referer}i\\" \\"%{User-Agent}i\\"" vhost_combined/LogFormat "%v:%p %h %l %u %t \\"%r\\" %>s %O %D \\"%{Referer}i\\" \\"%{User-Agent}i\\"" vhost_combined/' /etc/apache2/apache2.conf
        APACHE_MODIFIED=1
    fi
    
    # Update combined format
    if grep -q 'LogFormat "%h %l %u %t \\"%r\\" %>s %O \\"%{Referer}i\\" \\"%{User-Agent}i\\"" combined' /etc/apache2/apache2.conf; then
        sed -i 's/LogFormat "%h %l %u %t \\"%r\\" %>s %O \\"%{Referer}i\\" \\"%{User-Agent}i\\"" combined/LogFormat "%h %l %u %t \\"%r\\" %>s %O %D \\"%{Referer}i\\" \\"%{User-Agent}i\\"" combined/' /etc/apache2/apache2.conf
        APACHE_MODIFIED=1
    fi
    
    # Update common format
    if grep -q 'LogFormat "%h %l %u %t \\"%r\\" %>s %O" common' /etc/apache2/apache2.conf; then
        sed -i 's/LogFormat "%h %l %u %t \\"%r\\" %>s %O" common/LogFormat "%h %l %u %t \\"%r\\" %>s %O %D" common/' /etc/apache2/apache2.conf
        APACHE_MODIFIED=1
    fi
    
    # Restart Apache if modified
    if [ $APACHE_MODIFIED -eq 1 ]; then
        echo "Apache logging formats updated, restarting Apache service"
        systemctl restart apache2
    else
        echo "Apache logging formats already include response time or custom format is used"
    fi
else
    echo "Apache configuration not found, skipping LogFormat modifications"
fi

# Restart rsyslog service to apply all changes
systemctl restart rsyslog
echo "Rsyslog configured and restarted"

# Reload systemd to recognize the new service
systemctl daemon-reload

# Enable the service to start on boot
systemctl enable monitoring-agent

# Start the service
systemctl start monitoring-agent

echo "Monitoring agent installed and started successfully with agent ID: $AGENT_ID"
