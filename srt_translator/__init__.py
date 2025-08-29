"""SRT Translator package."""

from flask import Flask
import importlib.util
from pathlib import Path


def create_app():
    """Application factory pattern."""
    # Load the legacy app from venv/app.py for incremental refactoring
    backend_path = Path(__file__).resolve().parents[1] / "venv" / "app.py"
    spec = importlib.util.spec_from_file_location("legacy_app", str(backend_path))
    legacy_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy_module)
    
    # Return the legacy app directly for now to maintain compatibility
    # This allows for incremental refactoring without breaking existing functionality
    return legacy_module.app
