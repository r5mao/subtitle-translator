"""Normalize OpenSubtitles list JSON into UI rows, suggestions, and pagination meta."""
from __future__ import annotations

from .feature_display import (
    clean_work_search_query,
    filter_subtitle_rows_by_query,
    filter_work_suggestions_by_query,
)
from .flatten import (
    flatten_subtitle_results,
    total_count_from_response,
    total_pages_from_response,
)
from .media_poster import _maybe_absolutize_opensubtitles_image_url
from .work_suggestions import distinct_work_suggestions_from_subtitles

__all__ = [
    "clean_work_search_query",
    "distinct_work_suggestions_from_subtitles",
    "filter_subtitle_rows_by_query",
    "filter_work_suggestions_by_query",
    "flatten_subtitle_results",
    "total_count_from_response",
    "total_pages_from_response",
    "_maybe_absolutize_opensubtitles_image_url",
]
