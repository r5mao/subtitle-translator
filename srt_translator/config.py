"""Configuration settings for SRT Translator."""
import os
from pathlib import Path

class Config:
    """Base configuration."""
    # Use a default secret key for convenience in hobby projects
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change-in-production'
    
    # File upload settings
    # Go up two levels from this file (srt_translator/config.py -> srt_translator -> root)
    BASE_DIR = Path(__file__).resolve().parent.parent
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
    ALLOWED_EXTENSIONS = {'srt', 'ass', 'sub'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload size
    
    # Translation settings
    DEFAULT_TARGET_LANGUAGE = 'en'
    
    # Flask settings
    DEBUG = True  # Default to debug mode for hobby project
    TESTING = False

    # Ensure upload directory exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
