"""OpenSubtitles API id normalization (no HTTP)."""
from __future__ import annotations

from typing import Any, Optional


def normalize_opensubtitles_imdb_id(raw: Any) -> Optional[str]:
    """Numeric IMDb id for GET /subtitles (no ``tt`` prefix)."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s.startswith("tt"):
        s = s[2:]
    return s if s.isdigit() else None
