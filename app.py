#!/usr/bin/env python3
"""
Main application entry point using the new app factory pattern.
This allows running the app with: python app.py
"""
from srt_translator import create_app

# Environment variables are loaded in create_app() from the project-root .env

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
