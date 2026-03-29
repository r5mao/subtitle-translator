"""OpenSubtitles proxy routes (registered on api blueprint)."""
import logging
import os
import re
import tempfile
import uuid

from flask import jsonify, request

from srt_translator.services.opensubtitles_client import (
    OpenSubtitlesClient,
    OpenSubtitlesError,
    OpenSubtitlesNotConfigured,
    flatten_subtitle_results,
    total_pages_from_response,
)
from srt_translator.services.opensubtitles_lang import ui_lang_to_opensubtitles

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    name = name.strip() or "subtitle.srt"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:180]


def register_opensubtitles_routes(api_bp):
    @api_bp.route("/opensubtitles/status", methods=["GET"])
    def opensubtitles_status():
        c = OpenSubtitlesClient()
        return jsonify({"configured": c.configured()})

    @api_bp.route("/opensubtitles/search", methods=["POST"])
    def opensubtitles_search():
        c = OpenSubtitlesClient()
        if not c.configured():
            return jsonify({"error": "OpenSubtitles is not configured on this server."}), 503
        try:
            body = request.get_json(silent=True) or {}
            query = (body.get("query") or "").strip()
            if not query:
                return jsonify({"error": "query is required"}), 400
            ui_lang = (body.get("language") or "").strip()
            os_langs = ui_lang_to_opensubtitles(ui_lang) if ui_lang else ""
            page = int(body.get("page") or 1)
            raw = c.search(query, languages=os_langs, page=page)
            rows = flatten_subtitle_results(raw)
            tp = total_pages_from_response(raw)
            return jsonify(
                {
                    "results": rows,
                    "page": page,
                    "totalPages": tp,
                    "totalCount": len(rows),
                }
            )
        except OpenSubtitlesNotConfigured as e:
            return jsonify({"error": str(e)}), 503
        except OpenSubtitlesError as e:
            logger.warning("OpenSubtitles search: %s", e)
            return jsonify({"error": str(e)}), 502
        except ValueError:
            return jsonify({"error": "Invalid page"}), 400

    @api_bp.route("/opensubtitles/fetch", methods=["POST"])
    def opensubtitles_fetch():
        c = OpenSubtitlesClient()
        if not c.configured():
            return jsonify({"error": "OpenSubtitles is not configured on this server."}), 503
        body = request.get_json(silent=True) or {}
        file_id = str(body.get("file_id") or body.get("fileId") or "").strip()
        if not file_id:
            return jsonify({"error": "file_id is required"}), 400
        try:
            raw, fname = c.download_file(file_id)
            fetched_id = str(uuid.uuid4())
            safe = _safe_filename(fname)
            temp_dir = tempfile.gettempdir()
            path = os.path.join(temp_dir, f"{fetched_id}_{safe}")
            with open(path, "wb") as f:
                f.write(raw)
            ext = os.path.splitext(safe)[1].lower().lstrip(".") or "srt"
            return jsonify({"fetchedId": fetched_id, "filename": safe, "format": ext})
        except OpenSubtitlesNotConfigured as e:
            return jsonify({"error": str(e)}), 503
        except OpenSubtitlesError as e:
            logger.warning("OpenSubtitles fetch: %s", e)
            return jsonify({"error": str(e)}), 502
