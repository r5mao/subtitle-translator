"""TMDb API: poster, backdrop, display title, and year from tmdb_id (server-side only)."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, NamedTuple, Optional

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = os.environ.get("OPENSUBTITLES_USER_AGENT", "SubtitleTranslatorApp 1.0")


class TmdbBundle(NamedTuple):
    poster: Optional[str]
    backdrop: Optional[str]
    display_title: Optional[str]
    display_year: Optional[int]


def _poster_url_from_path(path: Any, size: str) -> Optional[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        return None
    return f"https://image.tmdb.org/t/p/{size}{path}"


def _year_from_date(val: Any) -> Optional[int]:
    if not isinstance(val, str) or len(val) < 4:
        return None
    if not val[:4].isdigit():
        return None
    y = int(val[:4])
    if 1950 <= y <= 2035:
        return y
    return None


def _bundle_from_movie(data: dict[str, Any]) -> TmdbBundle:
    raw_t = data.get("title") or data.get("original_title")
    title = raw_t.strip() if isinstance(raw_t, str) and raw_t.strip() else None
    y = _year_from_date(data.get("release_date"))
    poster = _poster_url_from_path(data.get("poster_path"), "w185")
    backdrop = _poster_url_from_path(data.get("backdrop_path"), "w780")
    return TmdbBundle(poster, backdrop, title, y)


def _bundle_from_tv(data: dict[str, Any]) -> TmdbBundle:
    raw_t = data.get("name") or data.get("original_name")
    title = raw_t.strip() if isinstance(raw_t, str) and raw_t.strip() else None
    y = _year_from_date(data.get("first_air_date"))
    poster = _poster_url_from_path(data.get("poster_path"), "w185")
    backdrop = _poster_url_from_path(data.get("backdrop_path"), "w780")
    return TmdbBundle(poster, backdrop, title, y)


def _fetch_tmdb_details(kind: str, tid: int, api_key: str) -> Optional[dict[str, Any]]:
    qs = urllib.parse.urlencode({"api_key": api_key})
    url = f"https://api.themoviedb.org/3/{kind}/{tid}?{qs}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": _DEFAULT_USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        logger.debug("TMDb %s details %s: HTTP %s", kind, tid, e.code)
        return None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as e:
        logger.debug("TMDb %s details %s: %s", kind, tid, e)
        return None
    return raw if isinstance(raw, dict) else None


def tmdb_bundle_for_id(tmdb_raw: Any, cache: dict[int, TmdbBundle]) -> TmdbBundle:
    """
    One TMDb GET /movie/{id} or /tv/{id} per id (cached). Requires TMDB_API_KEY.
    Tries movie first, then TV (404 → next).
    """
    api_key = (os.environ.get("TMDB_API_KEY") or "").strip()
    if not api_key:
        return TmdbBundle(None, None, None, None)
    try:
        tid = int(tmdb_raw)
    except (TypeError, ValueError):
        return TmdbBundle(None, None, None, None)
    if tid <= 0:
        return TmdbBundle(None, None, None, None)
    if tid in cache:
        return cache[tid]
    for kind, parser in (("movie", _bundle_from_movie), ("tv", _bundle_from_tv)):
        raw = _fetch_tmdb_details(kind, tid, api_key)
        if raw is None:
            continue
        bundle = parser(raw)
        if (
            bundle.poster
            or bundle.backdrop
            or bundle.display_title
            or bundle.display_year is not None
        ):
            cache[tid] = bundle
            return bundle
    empty = TmdbBundle(None, None, None, None)
    cache[tid] = empty
    return empty


def tmdb_poster_and_backdrop_for_id(
    tmdb_raw: Any, cache: dict[int, TmdbBundle]
) -> tuple[Optional[str], Optional[str]]:
    """Backward-compatible wrapper: poster (w185) and backdrop (w780) from bundle."""
    b = tmdb_bundle_for_id(tmdb_raw, cache)
    return (b.poster, b.backdrop)
