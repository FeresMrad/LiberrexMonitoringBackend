"""Socket.IO event handlers with JWT authentication."""
from flask import request
from flask_socketio import join_room, leave_room, disconnect
from app.auth import validate_token

def register_socket_events(socketio, host_subscribers):
    """Register Socket.IO event handlers with the socketio instance."""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection with authentication."""
        token = request.args.get('token')
        
        if not token:
            print(f'Client {request.sid} attempted connection without token')
            disconnect()
            return False
            
        payload = validate_token(token)
        if not payload:
            print(f'Client {request.sid} provided invalid token')
            disconnect()
            return False
        
        # Store user data for this socket session
        request.socket_user = payload
        print(f'Client {request.sid} connected as {payload["user_id"]}')

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        user_id = getattr(request, 'socket_user', {}).get('user_id', 'unknown')
        print(f'Client {request.sid} ({user_id}) disconnected')

        # Clean up subscriptions for this socket
        for host in list(host_subscribers.keys()):
            if host_subscribers[host] and request.sid in host_subscribers[host]:
                host_subscribers[host].remove(request.sid)
                print(f'Removed client {request.sid} from host {host} subscribers')

    @socketio.on('subscribe')
    def handle_subscribe(data):
        """Handle client subscription to a host with access control."""
        host = data.get('host')
        if not host:
            return
        
        # Check if user has permission to subscribe to this host
        allowed_hosts = getattr(request, 'socket_user', {}).get('allowed_hosts', [])
        if host not in allowed_hosts:
            print(f'Client {request.sid} unauthorized access attempt to host {host}')
            return

        # Add client to host room
        join_room(host)

        # Add client to subscribers list
        if host not in host_subscribers:
            host_subscribers[host] = set()
        host_subscribers[host].add(request.sid)

        user_id = getattr(request, 'socket_user', {}).get('user_id', 'unknown')
        print(f'Client {request.sid} ({user_id}) subscribed to host {host}')

    @socketio.on('unsubscribe')
    def handle_unsubscribe(data):
        """Handle client unsubscription from a host."""
        host = data.get('host')
        if not host:
            return

        # Remove client from host room
        leave_room(host)

        # Remove client from subscribers list
        if host in host_subscribers and request.sid in host_subscribers[host]:
            host_subscribers[host].remove(request.sid)

        user_id = getattr(request, 'socket_user', {}).get('user_id', 'unknown')
        print(f'Client {request.sid} ({user_id}) unsubscribed from host {host}')
