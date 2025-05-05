"""MySQL database configuration and connection management."""
import os
from flask import g
import mysql.connector
from mysql.connector import pooling

def get_mysql_config():
    """Get MySQL configuration from environment variables."""
    return {
        'host': os.getenv('MYSQL_HOST'),
        'port': int(os.getenv('MYSQL_PORT')),
        'user': os.getenv('MYSQL_USER'),
        'password': os.getenv('MYSQL_PASSWORD'),
        'database': os.getenv('MYSQL_DATABASE'),
    }

# Create a connection pool
connection_pool = None

def init_db_pool(app):
    """Initialize the database connection pool."""
    global connection_pool
    
    # Get MySQL configuration
    mysql_config = get_mysql_config()
    
    # Create a connection pool
    connection_pool = pooling.MySQLConnectionPool(
        pool_name="liberrex_pool",
        pool_size=5,
        **mysql_config
    )
    
    # Log successful connection
    app.logger.info(f"MySQL connection pool initialized: {mysql_config['host']}:{mysql_config['port']}")

def get_db():
    """Get a database connection from the pool."""
    if 'db' not in g:
        g.db = connection_pool.get_connection()
    
    return g.db

def close_db(e=None):
    """Close the database connection."""
    db = g.pop('db', None)
    
    if db is not None:
        db.close()

def init_app(app):
    """Initialize MySQL with the Flask app."""
    # Initialize the connection pool
    init_db_pool(app)
    
    # Register close_db function to be called when the application context ends
    app.teardown_appcontext(close_db)
