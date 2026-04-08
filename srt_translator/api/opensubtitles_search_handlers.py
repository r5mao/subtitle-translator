"""OpenSubtitles search, fetch, download, preview API routes."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid
from typing import Optional

from flask import jsonify, request, send_file

from srt_translator.services.fetched_subtitle_file import (
    is_valid_fetched_id,
    resolve_fetched_subtitle_file,
)
from srt_translator.services.opensubtitles_client import (
    OpenSubtitlesClient,
    OpenSubtitlesError,
    OpenSubtitlesNotConfigured,
    distinct_work_suggestions_from_subtitles,
    filter_subtitle_rows_by_query,
    filter_work_suggestions_by_query,
    flatten_subtitle_results,
    get_language_name_lookup,
    normalize_opensubtitles_imdb_id,
    total_count_from_response,
    total_pages_from_response,
)
from srt_translator.services.opensubtitles_lang import ui_lang_to_opensubtitles
from srt_translator.services.subtitle_preview import (
    build_subtitle_preview_json,
    decode_subtitle_bytes,
)

logger = logging.getLogger(__name__)

_ALLOWED_PER_PAGE = frozenset({10, 25, 50, 100})
_MAX_SEARCH_PAGES = 10
_SUGGESTIONS_MAX = 10
_SUGGESTIONS_FETCH_PER_PAGE = 50
_SUGGEST_QUERY_MIN_LEN = 2
_SUGGEST_QUERY_MAX_LEN = 200


def _safe_filename(name: str) -> str:
    name = name.strip() or "subtitle.srt"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:180]


def register_opensubtitles_search_routes(api_bp) -> None:
    @api_bp.route("/opensubtitles/status", methods=["GET"])
    def opensubtitles_status():
        c = OpenSubtitlesClient()
        return jsonify({"configured": c.configured()})

    @api_bp.route("/opensubtitles/search", methods=["POST"])
    def opensubtitles_search():
        c = OpenSubtitlesClient()
        if not c.configured():
            return jsonify(
                {"error": "OpenSubtitles is not configured on this server."}
            ), 503
        try:
            body = request.get_json(silent=True) or {}
            query = (body.get("query") or "").strip()
            if not query:
                return jsonify({"error": "query is required"}), 400
            ui_lang = (body.get("language") or "").strip()
            os_langs = ui_lang_to_opensubtitles(ui_lang) if ui_lang else ""
            page = int(body.get("page") or 1)
            if page < 1 or page > _MAX_SEARCH_PAGES:
                return jsonify({"error": "Invalid page"}), 400
            raw_per = body.get("perPage", body.get("per_page", 10))
            try:
                per_page = int(raw_per)
            except (TypeError, ValueError):
                per_page = 10
            if per_page not in _ALLOWED_PER_PAGE:
                per_page = 10
            year_val: Optional[int] = None
            yr = body.get("year")
            if yr is not None and yr != "":
                try:
                    yi = int(yr)
                    if 1870 <= yi <= 2100:
                        year_val = yi
                except (TypeError, ValueError):
                    pass
            imdb_q = normalize_opensubtitles_imdb_id(
                body.get("imdbId") or body.get("imdb_id")
            )
            lang_lookup = get_language_name_lookup(c)
            raw = c.search(
                query,
                languages=os_langs,
                page=page,
                per_page=per_page,
                year=year_val,
                imdb_id=imdb_q,
            )
            _api_data = raw.get("data")
            _refine_active = year_val is not None or bool(imdb_q)
            if _refine_active and isinstance(_api_data, list) and len(_api_data) == 0:
                raw = c.search(
                    query,
                    languages=os_langs,
                    page=page,
                    per_page=per_page,
                    year=None,
                    imdb_id=None,
                )
            rows = flatten_subtitle_results(raw, language_names=lang_lookup)
            rows = filter_subtitle_rows_by_query(rows, query)
            if len(rows) > per_page:
                rows = rows[:per_page]
            tp = total_pages_from_response(raw)
            if tp is not None:
                tp = min(tp, _MAX_SEARCH_PAGES)
            tc = total_count_from_response(raw)
            if tc is None:
                tc = len(rows)
            return jsonify(
                {
                    "results": rows,
                    "page": page,
                    "perPage": per_page,
                    "totalPages": tp,
                    "totalCount": tc,
                }
            )
        except OpenSubtitlesNotConfigured as e:
            return jsonify({"error": str(e)}), 503
        except OpenSubtitlesError as e:
            logger.warning("OpenSubtitles search: %s", e)
            return jsonify({"error": str(e)}), 502
        except ValueError:
            return jsonify({"error": "Invalid page"}), 400

    @api_bp.route("/opensubtitles/suggestions", methods=["POST"])
    def opensubtitles_suggestions():
        c = OpenSubtitlesClient()
        if not c.configured():
            return jsonify(
                {"error": "OpenSubtitles is not configured on this server."}
            ), 503
        try:
            body = request.get_json(silent=True) or {}
            query = (body.get("query") or "").strip()
            if len(query) < _SUGGEST_QUERY_MIN_LEN:
                return jsonify(
                    {
                        "error": f"query must be at least {_SUGGEST_QUERY_MIN_LEN} characters"
                    }
                ), 400
            if len(query) > _SUGGEST_QUERY_MAX_LEN:
                return jsonify({"error": "query too long"}), 400
            raw = c.search(
                query,
                languages="",
                page=1,
                per_page=_SUGGESTIONS_FETCH_PER_PAGE,
            )
            suggestions = distinct_work_suggestions_from_subtitles(
                raw, limit=_SUGGESTIONS_MAX
            )
            suggestions = filter_work_suggestions_by_query(suggestions, query)
            return jsonify({"suggestions": suggestions})
        except OpenSubtitlesNotConfigured as e:
            return jsonify({"error": str(e)}), 503
        except OpenSubtitlesError as e:
            logger.warning("OpenSubtitles suggestions: %s", e)
            return jsonify({"error": str(e)}), 502

    @api_bp.route("/opensubtitles/fetch", methods=["POST"])
    def opensubtitles_fetch():
        c = OpenSubtitlesClient()
        if not c.configured():
            return jsonify(
                {"error": "OpenSubtitles is not configured on this server."}
            ), 503
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

    @api_bp.route("/opensubtitles/fetched/<fetched_id>/download", methods=["GET"])
    def opensubtitles_fetched_download(fetched_id):
        if not is_valid_fetched_id(fetched_id):
            return jsonify({"error": "Invalid fetched subtitle id"}), 400
        resolved = resolve_fetched_subtitle_file(fetched_id)
        if not resolved:
            return jsonify({"error": "Fetched subtitle expired or not found."}), 404
        path, name = resolved
        try:
            return send_file(
                path,
                as_attachment=True,
                download_name=name,
                mimetype="application/octet-stream",
            )
        except OSError as e:
            logger.warning("Fetched download read error: %s", e)
            return jsonify({"error": "Could not read subtitle file"}), 500

    @api_bp.route(
        "/opensubtitles/fetched/<fetched_id>/preview", methods=["GET", "POST"]
    )
    def opensubtitles_fetched_preview(fetched_id):
        if not is_valid_fetched_id(fetched_id):
            return jsonify({"error": "Invalid fetched subtitle id"}), 400
        resolved = resolve_fetched_subtitle_file(fetched_id)
        if not resolved:
            return jsonify({"error": "Fetched subtitle expired or not found."}), 404
        path, _name = resolved
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            logger.warning("Fetched preview read error: %s", e)
            return jsonify({"error": "Could not read subtitle file"}), 500
        content = decode_subtitle_bytes(raw)
        if content is None:
            empty = {
                "sampleLines": [],
                "originalLines": [],
                "translatedLines": None,
                "pinyinLines": None,
                "layout": "single",
                "format": "unknown",
            }
            return jsonify(empty)
        if request.method == "GET":
            return jsonify(
                build_subtitle_preview_json(
                    content,
                    source_language="",
                    target_language="",
                    dual_language=False,
                    wants_translate=False,
                )
            )
        body = request.get_json(silent=True) or {}
        src = (body.get("sourceLanguage") or "").strip()
        tgt = (body.get("targetLanguage") or "").strip()
        dual = str(body.get("dualLanguage", "false")).strip().lower() in (
            "true",
            "on",
            "1",
            "yes",
        )
        wants = str(body.get("wantsTranslate", "true")).strip().lower() in (
            "true",
            "on",
            "1",
            "yes",
        )
        return jsonify(
            build_subtitle_preview_json(
                content,
                source_language=src,
                target_language=tgt,
                dual_language=dual,
                wants_translate=wants,
            )
        )
