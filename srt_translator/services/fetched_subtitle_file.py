"""Resolve OpenSubtitles fetched subtitle temp files on disk (shared by translate + download)."""
import os
import re
import tempfile
from typing import Optional, Tuple

_FETCHED_UUID_RE = re.compile(r"^[a-f0-9-]{36}$")


def is_valid_fetched_id(fetched_id: str) -> bool:
    return bool(_FETCHED_UUID_RE.match((fetched_id or "").strip()))


def resolve_fetched_subtitle_file(fetched_id: str) -> Optional[Tuple[str, str]]:
    """
    Return (absolute_path, stored_filename_after_uuid_prefix) if the temp file exists.
    None if the id format is invalid or no matching file (caller may distinguish via is_valid_fetched_id).
    """
    fid = (fetched_id or "").strip()
    if not is_valid_fetched_id(fid):
        return None
    temp_dir = tempfile.gettempdir()
    prefix = f"{fid}_"
    matches = [f for f in os.listdir(temp_dir) if f.startswith(prefix)]
    if not matches:
        return None
    fname_key = matches[0]
    path = os.path.join(temp_dir, fname_key)
    original_filename = fname_key[len(prefix) :]
    return (path, original_filename)
