"""SRT Translator package."""

from flask import Flask, send_from_directory
import os
from pathlib import Path
from .api import api_bp


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__, 
               static_folder=os.path.abspath('static'),
               template_folder=os.path.abspath('.'))
    
    # Load configuration
    app.config.from_object('srt_translator.config.Config')
    
    # Initialize extensions
    from .services import translation
    
    # Register blueprints
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Serve index.html for the root URL
    @app.route('/')
    def index():
        return send_from_directory(os.path.abspath('.'), 'index.html')
    
    # Add favicon route
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(
            os.path.abspath('static'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )
    
    return app
