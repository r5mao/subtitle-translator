"""API blueprint for SRT Translator."""
from flask import Blueprint, jsonify, request

api_bp = Blueprint('api', __name__)

# Routes will be registered here
@api_bp.route('/health')
def health_check():
    """Basic health check endpoint."""
    return jsonify({'status': 'ok'})
