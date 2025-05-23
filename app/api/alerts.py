"""Simplified alert API endpoints."""
from flask import Blueprint, jsonify, request, current_app
from app.alerts.rules import (
    get_all_rules, get_rule_by_id, create_rule, update_rule, delete_rule
)
from app.mysql import get_db
from app.auth import require_admin, require_auth

# Create a blueprint for alert endpoints
alerts_bp = Blueprint('alerts', __name__, url_prefix='/alerts')

@alerts_bp.route('/rules', methods=['GET'])
@require_auth
def get_rules():
    """Get all alert rules."""
    rules = get_all_rules()
    return jsonify(rules)

@alerts_bp.route('/rules/<rule_id>', methods=['GET'])
@require_auth
def get_rule(rule_id):
    """Get a specific alert rule."""
    rule = get_rule_by_id(rule_id)
    
    if not rule:
        return jsonify({"error": "Rule not found"}), 404
    
    return jsonify(rule)

@alerts_bp.route('/rules', methods=['POST'])
@require_admin
def add_rule():
    """Create a new alert rule with separate notification settings."""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Validate required fields
    required_fields = ['name', 'metric_type']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Field '{field}' is required"}), 400
    
    # For non-uptime rules, also require comparison and threshold
    if data.get('metric_type') != 'uptime.status':
        if 'comparison' not in data:
            return jsonify({"error": "Field 'comparison' is required"}), 400
        if 'threshold' not in data:
            return jsonify({"error": "Field 'threshold' is required"}), 400
    else:
        # For uptime rules, set default comparison and threshold
        data['comparison'] = 'above'
        data['threshold'] = 60  # 60 seconds
    
    # Get notification settings directly
    notifications = data.get('notifications', {})
    email_enabled = notifications.get('email_enabled', False)
    sms_enabled = notifications.get('sms_enabled', False)
    
    # Handle breach duration/count
    min_breach_count = data.get('min_breach_count', 1)
    
    # Handle email threshold and duration
    email_threshold = None
    email_breach_count = None
    
    # Only process email threshold if email is enabled
    if email_enabled:
        email_threshold = data.get('email_threshold')
        email_breach_count = data.get('email_breach_count')
    
    # Handle SMS threshold and duration
    sms_threshold = None
    sms_breach_count = None
    if sms_enabled:
        sms_threshold = data.get('sms_threshold')
        sms_breach_count = data.get('sms_breach_count')

    # Create rule
    try:
        rule_id = create_rule(
            name=data['name'],
            description=data.get('description', ''),
            metric_type=data['metric_type'],
            comparison=data['comparison'],
            threshold=float(data['threshold']),
            targets=data.get('targets', [{'type': 'all', 'id': '*'}]),
            min_breach_count=min_breach_count,
            email_threshold=email_threshold,
            email_breach_count=email_breach_count,
            sms_threshold=sms_threshold,
            sms_breach_count=sms_breach_count
        )
        
        # Save notification settings
        update_rule(rule_id, {
            'notifications': {
                'email_enabled': email_enabled,
                'sms_enabled': sms_enabled,
                'email_recipients': '',  # Will be configured in backend
                'sms_recipients': ''
            }
        })
        
        # Update the uptime checker to pick up new rules
        from app.uptime_checker import update_uptime_checker
        update_uptime_checker(current_app)
        
        return jsonify({"success": True, "rule_id": rule_id}), 201
    
    except Exception as e:
        current_app.logger.error(f"Error creating alert rule: {e}")
        return jsonify({"error": str(e)}), 400

@alerts_bp.route('/rules/<rule_id>', methods=['PUT'])
@require_admin
def update_rule_endpoint(rule_id):
    """Update a specific alert rule."""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Check if rule exists
    rule = get_rule_by_id(rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404
    
    # Just process the updates directly
            
    # Handle email threshold and duration
    if 'notifications' in data:
        if data['notifications'].get('email_enabled', False):
            if 'email_threshold' in data:
                data['email_threshold'] = data['email_threshold']
            if 'email_breach_count' in data:
                data['email_breach_count'] = data['email_breach_count']
        else:
            # If email is disabled, clear email threshold settings
            data['email_threshold'] = None
            data['email_breach_count'] = None
            
        # Handle SMS threshold and duration similarly
        if data['notifications'].get('sms_enabled', False):
            if 'sms_threshold' in data:
                data['sms_threshold'] = data['sms_threshold']
            if 'sms_breach_count' in data:
                data['sms_breach_count'] = data['sms_breach_count']
        else:
            # If SMS is disabled, clear SMS threshold settings
            data['sms_threshold'] = None
            data['sms_breach_count'] = None
    
    # Update rule
    success = update_rule(rule_id, data)
    
    if not success:
        return jsonify({"error": "Failed to update rule"}), 400
    
    return jsonify({"success": True})

@alerts_bp.route('/rules/<rule_id>', methods=['DELETE'])
@require_admin
def delete_rule_endpoint(rule_id):
    """Delete a specific alert rule."""
    # Check if rule exists
    rule = get_rule_by_id(rule_id)
    if not rule:
        return jsonify({"error": "Rule not found"}), 404
    
    # Delete rule
    success = delete_rule(rule_id)
    
    if not success:
        return jsonify({"error": "Failed to delete rule"}), 400
    
    return jsonify({"success": True})

@alerts_bp.route('/events', methods=['GET'])
@require_auth
def get_alerts():
    """Get alert events with optional filtering."""
    status = request.args.get('status')
    host = request.args.get('host')
    
    # Get the current user's ID from the token
    user_id = request.user.get('user_id')
    user_role = request.user.get('role')
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Build query with optional filters
    query = """
    SELECT e.id, e.rule_id, e.host, e.status, e.value, 
           e.triggered_at, e.resolved_at, e.message, 
           COALESCE(r.name, 'Deleted Rule') as rule_name, 
           r.comparison, r.threshold, r.metric_type
    FROM alert_events e
    LEFT JOIN alert_rules r ON e.rule_id = r.id
    """

    conditions = []
    params = []
    
    # Apply status filter if provided
    if status:
        conditions.append("e.status = %s")
        params.append(status)
    
    # Apply host filter if provided
    if host:
        conditions.append("e.host = %s")
        params.append(host)
        
        # Check access to this specific host for non-admins
        if user_role != 'admin' and not can_access_host(user_id, host):
            return jsonify([])  # Return empty if no access
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY e.triggered_at DESC"
    
    cursor.execute(query, params)
    all_alerts = cursor.fetchall()
    cursor.close()
    
    # If admin, return all alerts
    if user_role == 'admin':
        return jsonify(all_alerts)
    
    # For regular users, filter by accessible hosts
    from app.auth import can_access_host
    
    filtered_alerts = []
    for alert in all_alerts:
        if can_access_host(user_id, alert['host']):
            filtered_alerts.append(alert)
    
    return jsonify(filtered_alerts)

@alerts_bp.route('/events/<alert_id>', methods=['DELETE'])
@require_auth
def delete_alert(alert_id):
    """Delete a specific alert event."""
    db = get_db()
    cursor = db.cursor()
    
    try:
        # Delete the alert event
        cursor.execute("DELETE FROM alert_events WHERE id = %s", (alert_id,))
        
        # Check if any rows were affected
        if cursor.rowcount == 0:
            db.rollback()
            return jsonify({"error": "Alert not found"}), 404
        
        db.commit()
        return jsonify({"success": True, "message": "Alert deleted successfully"})
    except Exception as e:
        current_app.logger.error(f"Error deleting alert: {e}")
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()

