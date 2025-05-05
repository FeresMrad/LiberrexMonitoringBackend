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

    # Initialize MySQL database
    from app import mysql
    mysql.init_app(app)
    
    # Initialize extensions with more permissive CORS settings
    cors.init_app(app, resources={r"/api/*": {"origins": "*", "supports_credentials": True, "methods": ["GET", "POST", "OPTIONS"]}})
    socketio.init_app(app, cors_allowed_origins="*")
    
    # Register blueprints
    from app.api import api_bp
    from app.webhook import webhook_bp
    
    app.register_blueprint(api_bp)
    app.register_blueprint(webhook_bp)
    
    # Add explicit CORS handling for preflight requests
    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response
    
    # Register socket events
    register_socket_events(socketio, host_subscribers)

    # Initialize alerts
    from app.alerts.engine import rebuild_alert_state
    with app.app_context():
        rebuild_alert_state()

    return app
