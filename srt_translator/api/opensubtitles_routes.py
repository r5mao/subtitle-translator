"""OpenSubtitles proxy routes (registered on api blueprint)."""

from __future__ import annotations

from srt_translator.api.opensubtitles_poster_proxy import register_poster_proxy_route
from srt_translator.api.opensubtitles_search_handlers import (
    register_opensubtitles_search_routes,
)


def register_opensubtitles_routes(api_bp) -> None:
    register_poster_proxy_route(api_bp)
    register_opensubtitles_search_routes(api_bp)
