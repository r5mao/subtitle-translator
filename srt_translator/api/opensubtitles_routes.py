"""OpenSubtitles proxy routes (registered on api blueprint)."""
import logging
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid

from flask import Response, jsonify, request, send_file

from srt_translator.services.opensubtitles_client import (
    OpenSubtitlesClient,
    OpenSubtitlesError,
    OpenSubtitlesNotConfigured,
    flatten_subtitle_results,
    get_language_name_lookup,
    total_count_from_response,
    total_pages_from_response,
)

_ALLOWED_PER_PAGE = frozenset({10, 25, 50, 100})
# UI and API only expose this many OpenSubtitles result pages (page 1..N).
_MAX_SEARCH_PAGES = 10
from srt_translator.services.opensubtitles_lang import ui_lang_to_opensubtitles
from srt_translator.services.fetched_subtitle_file import (
    is_valid_fetched_id,
    resolve_fetched_subtitle_file,
)
from srt_translator.services.subtitle_preview import (
    build_subtitle_preview_json,
    decode_subtitle_bytes,
)

logger = logging.getLogger(__name__)

_POSTER_ALLOWED_HOST_SUFFIXES = frozenset(
    {
        "osdb.link",
        "opensubtitles.com",
        "opensubtitles.org",
        "image.tmdb.org",
        "themoviedb.org",
        "cloudfront.net",
        "amazonaws.com",
    }
)
_POSTER_MAX_BYTES = 2 * 1024 * 1024
_POSTER_TIMEOUT_SEC = 15
_DEFAULT_USER_AGENT = os.environ.get("OPENSUBTITLES_USER_AGENT", "SubtitleTranslatorApp 1.0")


def _poster_remote_host_allowed(host: str) -> bool:
    h = (host or "").lower().rstrip(".")
    if not h:
        return False
    for suf in _POSTER_ALLOWED_HOST_SUFFIXES:
        if h == suf or h.endswith("." + suf):
            return True
    return False


def _safe_filename(name: str) -> str:
    name = name.strip() or "subtitle.srt"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:180]


def register_opensubtitles_routes(api_bp):
    @api_bp.route("/opensubtitles/poster-image", methods=["GET"])
    def opensubtitles_poster_image():
        raw = (request.args.get("url") or "").strip()
        if not raw:
            return jsonify({"error": "url is required"}), 400
        try:
            parts = urllib.parse.urlsplit(raw)
        except ValueError:
            return jsonify({"error": "invalid url"}), 400
        if parts.scheme not in ("https", "http"):
            return jsonify({"error": "only http(s) urls are allowed"}), 400
        if not _poster_remote_host_allowed(parts.hostname or ""):
            return jsonify({"error": "host not allowed"}), 400

        req = urllib.request.Request(
            raw,
            headers={"User-Agent": _DEFAULT_USER_AGENT, "Accept": "image/*,*/*;q=0.8"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=_POSTER_TIMEOUT_SEC) as resp:
                ctype = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip() or "image/jpeg"
                chunks: list[bytes] = []
                total = 0
                while True:
                    block = resp.read(65536)
                    if not block:
                        break
                    total += len(block)
                    if total > _POSTER_MAX_BYTES:
                        return jsonify({"error": "image too large"}), 400
                    chunks.append(block)
                data = b"".join(chunks)
        except urllib.error.HTTPError as e:
            logger.warning("Poster proxy HTTP %s for %s", e.code, raw[:120])
            return jsonify({"error": f"upstream HTTP {e.code}"}), 502
        except urllib.error.URLError as e:
            logger.warning("Poster proxy URL error: %s", e)
            return jsonify({"error": "could not fetch image"}), 502

        if not data:
            return jsonify({"error": "empty response"}), 502
        return Response(
            data,
            mimetype=ctype,
            headers={
                "Cache-Control": "public, max-age=3600",
            },
        )

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
            if page < 1 or page > _MAX_SEARCH_PAGES:
                return jsonify({"error": "Invalid page"}), 400
            raw_per = body.get("perPage", body.get("per_page", 10))
            try:
                per_page = int(raw_per)
            except (TypeError, ValueError):
                per_page = 10
            if per_page not in _ALLOWED_PER_PAGE:
                per_page = 10
            lang_lookup = get_language_name_lookup(c)
            raw = c.search(query, languages=os_langs, page=page, per_page=per_page)
            rows = flatten_subtitle_results(raw, language_names=lang_lookup)
            # One API row can expand to several file rows; cap so UI row count matches per_page.
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

    @api_bp.route("/opensubtitles/fetched/<fetched_id>/download", methods=["GET"])
    def opensubtitles_fetched_download(fetched_id):
        """Stream the temp file from a prior /opensubtitles/fetch; does not delete it."""
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

    @api_bp.route("/opensubtitles/fetched/<fetched_id>/preview", methods=["GET", "POST"])
    def opensubtitles_fetched_preview(fetched_id):
        """First cue preview: GET original-only; POST adds translation/pinyin from body."""
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
