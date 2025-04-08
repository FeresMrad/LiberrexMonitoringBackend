"""Socket.IO event handlers."""
from flask import request
from flask_socketio import join_room, leave_room


def register_socket_events(socketio, host_subscribers):
    """Register Socket.IO event handlers with the socketio instance."""
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        print(f'Client {request.sid} connected')

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        print(f'Client {request.sid} disconnected')

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

        # Add client to host room
        join_room(host)

        # Add client to subscribers list
        if host not in host_subscribers:
            host_subscribers[host] = set()
        host_subscribers[host].add(request.sid)

        print(f'Client {request.sid} subscribed to host {host}')

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

        print(f'Client {request.sid} unsubscribed from host {host}')
