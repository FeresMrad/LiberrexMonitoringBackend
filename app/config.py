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
    INFLUXDB_URL = os.getenv('INFLUXDB_URL')
    INFLUXDB_USER = os.getenv('INFLUXDB_USER')
    INFLUXDB_PASSWORD = os.getenv('INFLUXDB_PASSWORD')
    INFLUXDB_DATABASE = os.getenv('INFLUXDB_DATABASE')
    
    # VictoriaLogs configuration
    VICTORIALOGS_URL = os.getenv('VICTORIALOGS_URL')


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
