"""Socket.IO event handlers with JWT authentication."""
from flask import request, session
from flask_socketio import join_room, leave_room, disconnect
from app.auth import validate_token
from app.users import can_access_host

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
        
        # Store user data in a socket-specific dictionary instead
        socketio.server.environ[request.sid] = {'user': payload}
        print(f'Client {request.sid} connected as {payload["user_id"]}')

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        # Get user data from socketio.server.environ
        user_data = socketio.server.environ.get(request.sid, {}).get('user', {})
        user_id = user_data.get('user_id', 'unknown')
        print(f'Client {request.sid} ({user_id}) disconnected')

        # Clean up user data
        if request.sid in socketio.server.environ:
            del socketio.server.environ[request.sid]

        # Clean up subscriptions for this socket
        for host in list(host_subscribers.keys()):
            if host_subscribers[host] and request.sid in host_subscribers[host]:
                host_subscribers[host].remove(request.sid)
                print(f'Removed client {request.sid} from host {host} subscribers')

    @socketio.on('subscribe')
    def handle_subscribe(data):
        """Handle client subscription to a host."""
        host = data.get('host')
        if not host:
            return
        
        # Get user data from socketio.server.environ
        user_data = socketio.server.environ.get(request.sid, {}).get('user', {})
        user_id = user_data.get('user_id')
        
        if not user_id or not can_access_host(user_id, host):
            print(f'Client {request.sid} ({user_id}) attempted to subscribe to host {host} without permission')
            return
        
        # Add client to host room
        join_room(host)

        # Add client to subscribers list - simplified
        host_subscribers.setdefault(host, set()).add(request.sid)

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

        # Get user data from socketio.server.environ
        user_data = socketio.server.environ.get(request.sid, {}).get('user', {})
        user_id = user_data.get('user_id', 'unknown')
        print(f'Client {request.sid} ({user_id}) unsubscribed from host {host}')
