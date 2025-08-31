"""Configuration settings for SRT Translator."""
import os
from pathlib import Path

class Config:
    """Base configuration."""
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change-in-production'
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join(Path(__file__).parent.parent, 'uploads')
    ALLOWED_EXTENSIONS = {'srt'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload size
    
    # Translation settings
    DEFAULT_TARGET_LANGUAGE = 'en'
    
    # Ensure upload directory exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    WTF_CSRF_ENABLED = False
    UPLOAD_FOLDER = os.path.join(Path(__file__).parent.parent, 'tests', 'test_uploads')
    
    # Create test upload directory
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    if not SECRET_KEY:
        raise ValueError("No SECRET_KEY set for production")


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
