"""TMDb images API: poster and backdrop URLs from tmdb_id (server-side only)."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = os.environ.get("OPENSUBTITLES_USER_AGENT", "SubtitleTranslatorApp 1.0")


def _first_poster_from_images_payload(payload: Any) -> Optional[str]:
    posters = payload.get("posters") if isinstance(payload, dict) else None
    if isinstance(posters, list) and posters:
        fp = posters[0].get("file_path") if isinstance(posters[0], dict) else None
        if isinstance(fp, str) and fp.startswith("/"):
            return f"https://image.tmdb.org/t/p/w185{fp}"
    return None


def _first_backdrop_from_images_payload(payload: Any) -> Optional[str]:
    """Widescreen still for scene-style preview (TMDb backdrops)."""
    backdrops = payload.get("backdrops") if isinstance(payload, dict) else None
    if not isinstance(backdrops, list):
        return None
    for bd in backdrops:
        if not isinstance(bd, dict):
            continue
        fp = bd.get("file_path")
        if isinstance(fp, str) and fp.startswith("/"):
            return f"https://image.tmdb.org/t/p/w780{fp}"
    return None


def _fetch_images_payload(tid: int, kind: str, api_key: str) -> Optional[dict[str, Any]]:
    qs = urllib.parse.urlencode({"api_key": api_key})
    url = f"https://api.themoviedb.org/3/{kind}/{tid}/images?{qs}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": _DEFAULT_USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        logger.debug("TMDB %s images %s: HTTP %s", kind, tid, e.code)
        return None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as e:
        logger.debug("TMDB %s images %s: %s", kind, tid, e)
        return None
    return raw if isinstance(raw, dict) else None


def tmdb_poster_and_backdrop_for_id(
    tmdb_raw: Any, cache: dict[int, tuple[Optional[str], Optional[str]]]
) -> tuple[Optional[str], Optional[str]]:
    """Poster (w185) and backdrop (w780) from one TMDb images request per id. Uses TMDB_API_KEY env."""
    api_key = (os.environ.get("TMDB_API_KEY") or "").strip()
    if not api_key:
        return (None, None)
    try:
        tid = int(tmdb_raw)
    except (TypeError, ValueError):
        return (None, None)
    if tid <= 0:
        return (None, None)
    if tid in cache:
        return cache[tid]
    for kind in ("movie", "tv"):
        payload = _fetch_images_payload(tid, kind, api_key)
        if not payload:
            continue
        poster = _first_poster_from_images_payload(payload)
        backdrop = _first_backdrop_from_images_payload(payload)
        if poster or backdrop:
            cache[tid] = (poster, backdrop)
            return cache[tid]
    cache[tid] = (None, None)
    return (None, None)
