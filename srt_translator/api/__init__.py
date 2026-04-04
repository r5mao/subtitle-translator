"""API blueprint for SRT Translator."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from flask import Blueprint, jsonify

from srt_translator.services.translation import translation_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)

translation_progress: dict = {}


@api_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify service availability."""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "SRT Translation API",
        }
    )


@api_bp.route("/languages", methods=["GET"])
def get_supported_languages():
    """Returns list of supported languages for translation."""
    return jsonify(
        {
            "languages": translation_service.language_names,
            "count": len(translation_service.language_names),
        }
    )


@api_bp.route("/task", methods=["GET"])
def get_task_id():
    """Returns task_id."""
    task_id = str(uuid.uuid4())
    logger.info("Get task ID: %s", task_id)
    return jsonify({"ok": True, "taskId": task_id})


from srt_translator.api.translate_routes import register_translate_routes  # noqa: E402

register_translate_routes(api_bp, translation_progress)

from srt_translator.api.opensubtitles_routes import register_opensubtitles_routes  # noqa: E402

register_opensubtitles_routes(api_bp)
