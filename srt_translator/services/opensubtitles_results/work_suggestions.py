"""Distinct work suggestions from OpenSubtitles search JSON."""
from __future__ import annotations

from typing import Any, Optional

from srt_translator.services.opensubtitles_ids import normalize_opensubtitles_imdb_id

from .feature_display import (
    clean_work_search_query,
    looks_like_tv_feature,
    pick_year_for_work_suggestion,
    primary_title_from_feature,
    release_looks_like_tech_strip_tag,
    title_hint_from_sub_filename,
    title_is_placeholder,
)
from srt_translator.services.tmdb_poster import TmdbBundle

from .media_poster import included_resource_index, resolve_poster_and_backdrop


def _feature_dedupe_key(item: dict[str, Any]) -> str:
    rel = item.get("relationships")
    if isinstance(rel, dict):
        block = rel.get("feature")
        if isinstance(block, dict):
            data = block.get("data")
            refs: list[dict[str, Any]] = []
            if isinstance(data, dict):
                refs = [data]
            elif isinstance(data, list):
                refs = [x for x in data if isinstance(x, dict)]
            for ref in refs:
                rid = ref.get("id")
                if rid is None:
                    continue
                rtype = str(ref.get("type") or "feature")
                return f"{rtype}:{rid}"
    attr = item.get("attributes") or {}
    if not isinstance(attr, dict):
        attr = {}
    feat = attr.get("feature_details") or {}
    if not isinstance(feat, dict):
        feat = {}
    title = primary_title_from_feature(feat, attr) or str(attr.get("release") or "").strip()
    year = feat.get("year")
    season = feat.get("season_number")
    episode = feat.get("episode_number")
    return f"fallback:{title}|{year}|{season}|{episode}"


def _collect_file_names_from_items(items: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for item in items:
        attr = item.get("attributes") or {}
        if not isinstance(attr, dict):
            continue
        files = attr.get("files")
        if not isinstance(files, list):
            continue
        for f in files:
            if isinstance(f, dict):
                fn = f.get("file_name") or f.get("cd_number")
                if fn:
                    out.append(str(fn))
    return out


def _work_suggestion_from_subtitle_items(
    items: list[dict[str, Any]],
    included_index: dict[tuple[str, str], dict[str, Any]],
    tmdb_media_cache: dict[int, TmdbBundle],
) -> Optional[dict[str, Any]]:
    if not items:
        return None
    item = items[0]
    attr = item.get("attributes") or {}
    if not isinstance(attr, dict):
        attr = {}
    feat = attr.get("feature_details") or {}
    if not isinstance(feat, dict):
        feat = {}
    title = primary_title_from_feature(feat, attr)
    if title_is_placeholder(title):
        title = ""
    if not title:
        files = attr.get("files")
        if isinstance(files, list) and files and isinstance(files[0], dict):
            title = title_hint_from_sub_filename(str(files[0].get("file_name") or ""))
    if not title:
        rel_s = str(attr.get("release") or "").strip()
        if rel_s and not release_looks_like_tech_strip_tag(rel_s):
            title = rel_s
    if not title:
        return None
    rel_s = str(attr.get("release") or "").strip()
    all_filenames = _collect_file_names_from_items(items)
    poster_url, _bd, tmdb_title, tmdb_year = resolve_poster_and_backdrop(
        item, attr, feat, included_index, tmdb_media_cache
    )
    if tmdb_title:
        title = tmdb_title
    api_year = feat.get("year")
    looks_tv = looks_like_tv_feature(feat, attr)
    year = pick_year_for_work_suggestion(
        feat,
        api_year,
        all_filenames,
        rel_s,
        title,
        looks_tv=looks_tv,
    )
    if tmdb_year is not None:
        year = tmdb_year
    season = feat.get("season_number")
    episode = feat.get("episode_number")
    feature_type = feat.get("feature_type") or attr.get("feature_type")

    feature_id: Optional[str] = None
    rel = item.get("relationships")
    if isinstance(rel, dict):
        fb = rel.get("feature")
        if isinstance(fb, dict):
            data = fb.get("data")
            refs: list[dict[str, Any]] = []
            if isinstance(data, dict):
                refs = [data]
            elif isinstance(data, list):
                refs = [x for x in data if isinstance(x, dict)]
            for ref in refs:
                if ref.get("id") is not None:
                    feature_id = str(ref["id"])
                    break

    imdb_raw = feat.get("imdb_id") or feat.get("parent_imdb_id")
    imdb_id = normalize_opensubtitles_imdb_id(imdb_raw)

    return {
        "title": title,
        "searchQuery": clean_work_search_query(title, year),
        "year": year,
        "season": season,
        "episode": episode,
        "featureType": feature_type,
        "posterUrl": poster_url,
        "featureId": feature_id,
        "imdbId": imdb_id,
    }


def distinct_work_suggestions_from_subtitles(
    api_json: dict[str, Any],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Distinct movies/shows (one per JSON:API feature or fallback key) for typeahead.
    Only runs poster/TMDb resolution once per distinct work.
    """
    cap = max(1, min(25, int(limit)))
    items = api_json.get("data")
    if not isinstance(items, list):
        return []

    seen: dict[str, list[dict[str, Any]]] = {}
    key_order: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = _feature_dedupe_key(item)
        if key not in seen:
            seen[key] = []
            key_order.append(key)
        seen[key].append(item)

    idx = included_resource_index(api_json.get("included"))
    tmdb_media_cache: dict[int, TmdbBundle] = {}
    out: list[dict[str, Any]] = []
    for key in key_order:
        if len(out) >= cap:
            break
        sug = _work_suggestion_from_subtitle_items(seen[key], idx, tmdb_media_cache)
        if sug:
            out.append(sug)
    return out
