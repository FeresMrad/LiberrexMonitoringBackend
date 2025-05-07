"""Alert notification service."""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import current_app

def send_alert_notification(rule, host, value, message):
    """Send notifications for a triggered alert."""
    notifications = rule.get('notifications', {})
    severity = rule.get('severity', 'info')
    
    # Send email for warning and critical (when email is enabled)
    if severity in ['warning', 'critical'] and notifications.get('email_enabled', False):
        # Use global config for recipients instead of per-rule recipients
        recipients = current_app.config.get('ALERT_EMAIL_RECIPIENTS', '')
        if recipients:
            send_email_notification(rule, host, value, message, recipients)

def send_email_notification(rule, host, value, message, recipients):
    """Send an email notification for an alert."""
    try:
        # Get email settings from config
        smtp_server = current_app.config.get('SMTP_SERVER')
        smtp_port = current_app.config.get('SMTP_PORT')
        smtp_username = current_app.config.get('SMTP_USERNAME')
        smtp_password = current_app.config.get('SMTP_PASSWORD')
        from_email = current_app.config.get('ALERT_FROM_EMAIL')
        
        if not smtp_server or not from_email:
            current_app.logger.error("Email settings not configured")
            return

        host_display_name = get_host_display_name(host)

        # Create email message
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = recipients
        msg['Subject'] = f"ALERT [{rule['severity'].upper()}]: {rule['name']} - {host}"
        
        # Email body
        body = f"""
        <html>
        <body>
            <h2>Alert Triggered: {rule['name']}</h2>
            <p><strong>Host:</strong> {host_display_name}</p>
	    <p><strong>Host ID:</strong> {host}</p>
            <p><strong>Severity:</strong> {rule['severity'].upper()}</p>
            <p><strong>Message:</strong> {message}</p>
            <p><strong>Current Value:</strong> {value}</p>
            <p><strong>Threshold:</strong> {rule['threshold']} ({rule['comparison']})</p>
            <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Connect to SMTP server
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if smtp_username and smtp_password:
                server.starttls()
                server.login(smtp_username, smtp_password)
            
            server.send_message(msg)
        
        current_app.logger.info(f"Alert email sent for {rule['name']} on {host}")
    
    except Exception as e:
        current_app.logger.error(f"Error sending email notification: {e}")
def get_host_display_name(host_id):
    """Get the display name for a host (custom name or ID if no custom name exists)."""
    try:
        from app.services.influxdb import query_influxdb
        
        # Query the custom_name for this host
        query = f'SELECT last("custom_name") FROM "custom_data" WHERE "host" = \'{host_id}\''
        response = query_influxdb(query)
        
        if response["results"][0].get("series"):
            values = response["results"][0]["series"][0]["values"][0]
            custom_name = values[1]
            if custom_name:
                return custom_name
        
        return host_id  # Fallback to host ID if no custom name found
    except Exception as e:
        current_app.logger.error(f"Error getting host display name: {e}")
        return host_id  # Fallback to host ID on error
