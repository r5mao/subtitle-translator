"""SRT Translator package."""

from flask import Flask
from .api import api_bp


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object('srt_translator.config.Config')
    
    # Initialize extensions
    from .services import translation
    
    # Register blueprints
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Add a simple route for the root URL
    @app.route('/')
    def index():
        return {'app': 'SRT Translator API', 'version': '1.0.0'}
    
    return app
