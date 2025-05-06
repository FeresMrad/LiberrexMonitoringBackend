"""API blueprints initialization."""
from flask import Blueprint

# Create a main blueprint that will combine all others
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Import all sub-blueprints
from .auth import auth_bp
from .hosts import hosts_bp
from .metrics import metrics_bp
from .logs import logs_bp
from .ssh import ssh_bp
from .uptime import uptime_bp
from .debug import debug_bp
from .users import users_bp
from .groups import groups_bp
from .apache import apache_bp
from .alerts import alerts_bp
from .notifications import notifications_bp

# Register all sub-blueprints
api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(hosts_bp)
api_bp.register_blueprint(metrics_bp)
api_bp.register_blueprint(logs_bp)
api_bp.register_blueprint(ssh_bp)
api_bp.register_blueprint(uptime_bp)
api_bp.register_blueprint(debug_bp)
api_bp.register_blueprint(users_bp)
api_bp.register_blueprint(groups_bp)
api_bp.register_blueprint(apache_bp)
api_bp.register_blueprint(alerts_bp)
api_bp.register_blueprint(notifications_bp)

# Export the utility functions for use elsewhere
from .utils import parse_time_parameters, format_time_range_params
