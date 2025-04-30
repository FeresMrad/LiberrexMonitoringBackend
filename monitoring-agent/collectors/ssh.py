"""SSH sessions collector."""
import subprocess
import json
from influxdb_client import Point

def collect_ssh_sessions(host):
    """Collect active SSH sessions for the host."""
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

def create_ssh_point(host, sessions):
    """Create InfluxDB point for SSH sessions."""
    ssh_point = Point("ssh_sessions").tag("host", host)
    ssh_point.field("active_count", len(sessions))
    ssh_point.field("sessions_json", json.dumps(sessions))
    return ssh_point

def collect(host):
    """Collect SSH metrics for the host."""
    sessions = collect_ssh_sessions(host)
    return [create_ssh_point(host, sessions)]
