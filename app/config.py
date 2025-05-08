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

    # Twilio configuration
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER')
    TWILIO_TO_NUMBERS = os.getenv('TWILIO_TO_NUMBERS')

    # Mail configuration
    SMTP_SERVER = os.getenv('SMTP_SERVER')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    ALERT_FROM_EMAIL = os.getenv('ALERT_FROM_EMAIL')
    ALERT_EMAIL_RECIPIENTS = os.getenv('ALERT_EMAIL_RECIPIENTS')
    
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
