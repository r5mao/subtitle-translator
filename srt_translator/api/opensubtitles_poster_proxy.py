"""Same-origin proxy for poster/backdrop images (allowlisted hosts)."""
from __future__ import annotations

import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from flask import Response, jsonify, request

logger = logging.getLogger(__name__)

_POSTER_ALLOWED_HOST_SUFFIXES = frozenset(
    {
        "osdb.link",
        "opensubtitles.com",
        "opensubtitles.org",
        "image.tmdb.org",
        "themoviedb.org",
        "tmdb.org",
        "cloudfront.net",
        "amazonaws.com",
        "imdb.com",
        "media-amazon.com",
        "ssl-images-amazon.com",
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


def register_poster_proxy_route(api_bp) -> None:
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
