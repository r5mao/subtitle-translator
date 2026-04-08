"""Flatten OpenSubtitles list JSON into per-file UI rows and read pagination meta."""

from __future__ import annotations

from typing import Any, Optional

from srt_translator.services.tmdb_poster import TmdbBundle

from .feature_display import (
    pick_display_year,
    primary_title_from_feature,
    release_looks_like_tech_strip_tag,
    title_hint_from_sub_filename,
    title_is_placeholder,
)
from .media_poster import included_resource_index, resolve_poster_and_backdrop


def _safe_download_count(value: Any) -> Optional[int]:
    """Only return a count for Info column; ignore non-numeric API garbage."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _safe_fps(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        if 0 < f < 1000:
            return round(f, 3)
        return None
    if isinstance(value, str):
        try:
            f = float(value.strip().replace(",", "."))
            if 0 < f < 1000:
                return round(f, 3)
        except ValueError:
            pass
    return None


def flatten_subtitle_results(
    api_json: dict[str, Any],
    language_names: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    """
    Normalize OpenSubtitles list response into UI rows (one per downloadable file).
    Tolerates schema variations.
    language_names: optional map from OpenSubtitles language_code to display name.
    """
    rows: list[dict[str, Any]] = []
    items = api_json.get("data")
    if not isinstance(items, list):
        return rows

    included_index = included_resource_index(api_json.get("included"))
    tmdb_media_cache: dict[int, TmdbBundle] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        attr = item.get("attributes") or {}
        if not isinstance(attr, dict):
            attr = {}
        feat = attr.get("feature_details") or {}
        if not isinstance(feat, dict):
            feat = {}

        base_feature_title = primary_title_from_feature(feat, attr)
        year = feat.get("year")
        season = feat.get("season_number")
        episode = feat.get("episode_number")
        feature_type = feat.get("feature_type") or attr.get("feature_type")

        language = attr.get("language") or ""
        release = attr.get("release") or ""
        downloads = _safe_download_count(attr.get("download_count"))
        fps = _safe_fps(attr.get("fps"))
        hi = attr.get("hearing_impaired")
        machine = attr.get("machine_translated")
        trusted = attr.get("from_trusted")

        files = attr.get("files")
        if not isinstance(files, list) or not files:
            fid = attr.get("file_id") or attr.get("files_file_id")
            if fid is not None:
                _stub = (
                    (base_feature_title or "subtitle")
                    if not title_is_placeholder(base_feature_title)
                    else "subtitle"
                )
                files = [
                    {
                        "file_id": fid,
                        "file_name": attr.get("file_name")
                        or release
                        or f"{_stub}.{language}.srt",
                    }
                ]
            else:
                continue

        poster_url, backdrop_url, tmdb_title, tmdb_year = resolve_poster_and_backdrop(
            item, attr, feat, included_index, tmdb_media_cache
        )

        for f in files:
            if not isinstance(f, dict):
                continue
            fid = f.get("file_id")
            if fid is None:
                continue
            file_name = f.get("file_name") or f.get("cd_number") or str(fid)
            ext = ""
            if isinstance(file_name, str) and "." in file_name:
                ext = file_name.rsplit(".", 1)[-1].lower()
            lc = str(language or "").strip()
            lang_display = lc
            if language_names and lc:
                lang_display = (
                    language_names.get(lc)
                    or language_names.get(lc.lower())
                    or next(
                        (
                            language_names[k]
                            for k in language_names
                            if k.lower() == lc.lower()
                        ),
                        lc,
                    )
                )
            row_title = base_feature_title
            if title_is_placeholder(row_title):
                row_title = ""
            if not row_title:
                row_title = title_hint_from_sub_filename(str(file_name))
            rel_s = str(release or "").strip()
            if not row_title and rel_s and not release_looks_like_tech_strip_tag(rel_s):
                row_title = rel_s
            if not row_title:
                row_title = str(file_name) if file_name else "—"
            if tmdb_title:
                row_title = tmdb_title
            fn_s = str(file_name)
            display_year = pick_display_year(
                feat, year, fn_s, rel_s, display_title=row_title
            )
            if tmdb_year is not None:
                display_year = tmdb_year
            rows.append(
                {
                    "fileId": str(fid),
                    "title": row_title,
                    "year": display_year,
                    "season": season,
                    "episode": episode,
                    "featureType": feature_type,
                    "release": release,
                    "language": lc,
                    "languageName": lang_display,
                    "fileName": file_name,
                    "format": ext or "srt",
                    "downloads": downloads,
                    "fps": fps,
                    "hearingImpaired": bool(hi) if hi is not None else None,
                    "machineTranslated": bool(machine) if machine is not None else None,
                    "fromTrusted": bool(trusted) if trusted is not None else None,
                    "posterUrl": poster_url,
                    "backdropUrl": backdrop_url,
                }
            )

    return rows


def total_pages_from_response(api_json: dict[str, Any]) -> Optional[int]:
    meta = api_json.get("total_pages")
    if isinstance(meta, int):
        return meta
    m = api_json.get("meta") or {}
    if isinstance(m, dict):
        tp = m.get("total_pages")
        if isinstance(tp, int):
            return tp
    return None


def total_count_from_response(api_json: dict[str, Any]) -> Optional[int]:
    tc = api_json.get("total_count")
    if isinstance(tc, int):
        return tc
    m = api_json.get("meta") or {}
    if isinstance(m, dict):
        tc = m.get("total_count")
        if isinstance(tc, int):
            return tc
    return None
