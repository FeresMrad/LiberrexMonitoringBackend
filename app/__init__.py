"""Application factory module."""
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS

from app.config import get_config
from app.sockets import register_socket_events
import app.services  # Initialize services

# Initialize extensions
socketio = SocketIO()
cors = CORS()

# Dictionary to store active host subscriptions
host_subscribers = {}


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(get_config())
    
    # Initialize extensions
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})
    socketio.init_app(app, cors_allowed_origins="*")
    
    # Register blueprints
    from app.api import api_bp
    from app.webhook import webhook_bp
    
    app.register_blueprint(api_bp)
    app.register_blueprint(webhook_bp)
    
    # Register socket events
    register_socket_events(socketio, host_subscribers)
    
    return app
