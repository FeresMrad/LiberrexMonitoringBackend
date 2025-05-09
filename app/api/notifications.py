"""Notifications API endpoints."""
from flask import Blueprint, jsonify, request, current_app
from app.mysql import get_db
from app.auth import require_auth

# Create a blueprint for notification endpoints
notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

@notifications_bp.route('', methods=['GET'])
@require_auth
def get_notifications():
    """Get notifications for the current user."""
    user_id = request.user.get('user_id')
    limit = request.args.get('limit', 20, type=int)
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    # Query to get notifications
    query = """
        SELECT n.id, n.alert_id, n.user_id, n.read, n.created_at, 
               e.host, e.value, e.message, e.triggered_at, e.rule_id,
               r.name as rule_name, r.metric_type, r.comparison, r.threshold
        FROM notifications n
        JOIN alert_events e ON n.alert_id = e.id
        JOIN alert_rules r ON e.rule_id = r.id
        WHERE n.user_id = %s
        ORDER BY n.created_at DESC
        LIMIT %s
    """
    
    cursor.execute(query, (user_id, limit))
    notifications = cursor.fetchall()
    cursor.close()
    
    return jsonify(notifications)

@notifications_bp.route('/<notification_id>/read', methods=['PUT'])
@require_auth
def mark_notification_as_read(notification_id):
    """Mark a notification as read."""
    user_id = request.user.get('user_id')
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        # First, check if the notification belongs to this user
        cursor.execute("""
            SELECT user_id FROM notifications
            WHERE id = %s
        """, (notification_id,))
        
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            return jsonify({"error": "Notification not found or not authorized"}), 404
        
        # Mark as read
        cursor.execute("""
            UPDATE notifications
            SET `read` = TRUE
            WHERE id = %s AND user_id = %s
        """, (notification_id, user_id))
        
        db.commit()
        return jsonify({"success": True})
        
    except Exception as e:
        current_app.logger.error(f"Error marking notification as read: {e}")
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()

@notifications_bp.route('/read-all', methods=['PUT'])
@require_auth
def mark_all_notifications_as_read():
    """Mark all notifications as read for the current user."""
    user_id = request.user.get('user_id')
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            UPDATE notifications
            SET `read` = TRUE
            WHERE user_id = %s
        """, (user_id,))
        
        db.commit()
        return jsonify({"success": True})
        
    except Exception as e:
        current_app.logger.error(f"Error marking all notifications as read: {e}")
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()

@notifications_bp.route('/<notification_id>', methods=['DELETE'])
@require_auth
def delete_notification(notification_id):
    """Delete a notification."""
    user_id = request.user.get('user_id')
    
    db = get_db()
    cursor = db.cursor()
    
    try:
        # First, check if the notification belongs to this user
        cursor.execute("""
            SELECT user_id FROM notifications
            WHERE id = %s
        """, (notification_id,))
        
        result = cursor.fetchone()
        if not result or result[0] != user_id:
            return jsonify({"error": "Notification not found or not authorized"}), 404
        
        # Delete the notification
        cursor.execute("""
            DELETE FROM notifications
            WHERE id = %s AND user_id = %s
        """, (notification_id, user_id))
        
        db.commit()
        return jsonify({"success": True})
        
    except Exception as e:
        current_app.logger.error(f"Error deleting notification: {e}")
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
