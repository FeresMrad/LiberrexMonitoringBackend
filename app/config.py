"""Configuration management for the application."""
import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

class Config:
    """Base configuration."""
    # Flask configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'devsecretkey')
    DEBUG = False
    TESTING = False
    
    # InfluxDB configuration
    INFLUXDB_URL = os.getenv('INFLUXDB_URL', 'http://82.165.230.7:8086')
    INFLUXDB_USER = os.getenv('INFLUXDB_USER', 'liberrex')
    INFLUXDB_PASSWORD = os.getenv('INFLUXDB_PASSWORD', 'test')
    INFLUXDB_DATABASE = os.getenv('INFLUXDB_DATABASE', 'metrics')
    
    # VictoriaLogs configuration
    VICTORIALOGS_URL = os.getenv('VICTORIALOGS_URL', 'http://82.165.230.7:9428')


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class TestingConfig(Config):
    """Testing configuration."""
    DEBUG = True
    TESTING = True


class ProductionConfig(Config):
    """Production configuration."""
    # In production, ensure these are set in environment variables
    SECRET_KEY = os.getenv('SECRET_KEY')
    
    # Override default values with None to force setting in production
    INFLUXDB_PASSWORD = os.getenv('INFLUXDB_PASSWORD')


# Map config name to config class
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

def get_config():
    """Return the appropriate configuration object based on the environment."""
    config_name = os.getenv('FLASK_ENV', 'default')
    return config.get(config_name, config['default'])
