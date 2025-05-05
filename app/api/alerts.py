"""Alert API endpoints."""
from flask import Blueprint, jsonify, request
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
    """Create a new alert rule."""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    # Validate required fields
    required_fields = ['name', 'metric_type', 'comparison', 'threshold', 'severity']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Field '{field}' is required"}), 400
    
    # Create rule
    try:
        rule_id = create_rule(
            name=data['name'],
            description=data.get('description', ''),
            metric_type=data['metric_type'],
            comparison=data['comparison'],
            threshold=float(data['threshold']),
            duration_minutes=int(data.get('duration_minutes', 5)),
            severity=data['severity'],
            targets=data.get('targets', [{'type': 'all', 'id': '*'}]),
            notifications=data.get('notifications', {})
        )
        
        return jsonify({"success": True, "rule_id": rule_id}), 201
    
    except Exception as e:
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
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Build query with optional filters
    query = """
        SELECT e.id, e.rule_id, e.host, e.status, e.value, 
               e.triggered_at, e.acknowledged_at, e.resolved_at, 
               e.acknowledged_by, e.message, r.name as rule_name,
               r.severity
        FROM alert_events e
        JOIN alert_rules r ON e.rule_id = r.id
    """
    
    conditions = []
    params = []
    
    if status:
        conditions.append("e.status = %s")
        params.append(status)
    
    if host:
        conditions.append("e.host = %s")
        params.append(host)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY e.triggered_at DESC"
    
    cursor.execute(query, params)
    alerts = cursor.fetchall()
    cursor.close()
    
    return jsonify(alerts)

@alerts_bp.route('/events/<alert_id>/acknowledge', methods=['POST'])
@require_auth
def acknowledge_alert(alert_id):
    """Acknowledge an alert."""
    user_id = request.user.get('user_id')
    
    db = get_db()
    cursor = db.cursor()
    
    # Find alert and update its status
    cursor.execute("""
        UPDATE alert_events 
        SET status = 'acknowledged', acknowledged_at = CURRENT_TIMESTAMP, acknowledged_by = %s
        WHERE id = %s AND status = 'triggered'
    """, (user_id, alert_id))
    
    if cursor.rowcount == 0:
        db.rollback()
        cursor.close()
        return jsonify({"error": "Alert not found or already acknowledged"}), 404
    
    db.commit()
    cursor.close()
    
    return jsonify({"success": True})
