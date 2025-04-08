"""WSGI entry point."""
from app import create_app
from app import socketio

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    # Run the app with Socket.IO
    socketio.run(app, host='0.0.0.0', port=5000, debug=app.config.get('DEBUG', False))
