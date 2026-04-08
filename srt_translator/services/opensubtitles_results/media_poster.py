"""Poster and backdrop URLs from OpenSubtitles JSON:API payloads and TMDb fallback."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from srt_translator.services.tmdb_poster import TmdbBundle, tmdb_bundle_for_id


def _normalize_media_url(val: Any) -> Optional[str]:
    if not isinstance(val, str):
        return None
    u = val.strip()
    if not u:
        return None
    if u.startswith("//"):
        u = "https:" + u
    if u.lower().startswith(("http://", "https://")):
        return u
    return None


def _looks_like_image_url(url: str) -> bool:
    path = url.lower().split("?", 1)[0]
    if any(path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".jfif")):
        return True
    if "osdb.link" in url.lower() and "feature" in url.lower():
        return True
    if "image.tmdb.org" in url.lower():
        return True
    if "/pictures/" in path or "/posters/" in path or "/poster" in path or "/img/" in path:
        return True
    return False


_IMG_URL_IN_TEXT_RE = re.compile(
    r"https?://[^\s\"'<>]+?(?:\.(?:jpg|jpeg|png|webp|gif)|/features/[^\s\"'<>]+)",
    re.IGNORECASE,
)


def _maybe_absolutize_opensubtitles_image_url(u: Optional[str]) -> Optional[str]:
    """Turn site-relative poster paths into absolute https URLs."""
    if not u or not isinstance(u, str):
        return None
    s = u.strip()
    if s.startswith("//"):
        s = "https:" + s
    if s.startswith("/") and "/../" not in s:
        low = s.lower()
        if (
            any(low.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".jfif"))
            or "/pictures/" in low
            or "/posters/" in low
            or "/poster" in low
            or "/img/" in low
        ):
            return "https://www.opensubtitles.com" + s
    return _normalize_media_url(s)


def _deep_find_image_url_in_payload(attr: dict[str, Any], feat: dict[str, Any], max_depth: int = 7) -> Optional[str]:
    """Last-resort: scan nested JSON for strings that look like image URLs."""

    def walk(obj: Any, depth: int) -> Optional[str]:
        if depth > max_depth:
            return None
        if isinstance(obj, str):
            s = obj.strip()
            u = _normalize_media_url(s)
            if u and _looks_like_image_url(u):
                return u
            m = _IMG_URL_IN_TEXT_RE.search(s)
            if m:
                u2 = _normalize_media_url(m.group(0))
                if u2:
                    return u2
            return None
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and "password" in k.lower():
                    continue
                found = walk(v, depth + 1)
                if found:
                    return found
        if isinstance(obj, list):
            for it in obj:
                found = walk(it, depth + 1)
                if found:
                    return found
        return None

    for root in (feat, attr):
        found = walk(root, 0)
        if found:
            return found
    return None


def _coerce_related_links(raw: Any) -> Any:
    """API may return related_links as dict, list, or JSON string."""
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        if s.startswith(("{", "[")):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return None
        return None
    return raw


def _scalar_to_poster_url(val: Any) -> Optional[str]:
    """Accept absolute http(s) URLs or site-relative /... image paths."""
    if val is None:
        return None
    if isinstance(val, str):
        u = _normalize_media_url(val)
        if u:
            return u
        return _maybe_absolutize_opensubtitles_image_url(val)
    return None


def _poster_from_related_links_block(rl: Any) -> Optional[str]:
    rl = _coerce_related_links(rl)
    if isinstance(rl, dict):
        for key in (
            "img_url",
            "image_url",
            "imgUrl",
            "imageUrl",
            "poster",
            "picture_url",
            "pictureUrl",
            "thumbnail",
            "thumb",
            "cover",
        ):
            u = _scalar_to_poster_url(rl.get(key))
            if u:
                return u
        for v in rl.values():
            u = _scalar_to_poster_url(v)
            if u and _looks_like_image_url(u):
                return u
    if isinstance(rl, list):
        for item in rl:
            if isinstance(item, dict):
                for key in ("img_url", "image_url", "imgUrl", "imageUrl"):
                    u = _scalar_to_poster_url(item.get(key))
                    if u:
                        return u
                u = _scalar_to_poster_url(item.get("url"))
                if u and _looks_like_image_url(u):
                    return u
            u = _poster_from_related_links_block(item)
            if u:
                return u
    return None


def _poster_url_from_subtitle_attributes(
    attr: dict[str, Any],
    feat: dict[str, Any],
) -> Optional[str]:
    """Poster URL from subtitle (or feature) attribute blobs; schema varies by API version."""

    for block in (
        attr.get("related_links"),
        attr.get("relatedLinks"),
        feat.get("related_links"),
        feat.get("relatedLinks"),
    ):
        u = _poster_from_related_links_block(block)
        if u:
            return u

    for key in (
        "image",
        "poster_url",
        "posterUrl",
        "feature_image",
        "featureImage",
        "movie_image",
        "movieImage",
        "thumbnail",
        "poster",
    ):
        for src in (attr, feat):
            u = _scalar_to_poster_url(src.get(key))
            if u:
                return u

    return None


def included_resource_index(included: Any) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(included, list):
        return out
    for inc in included:
        if not isinstance(inc, dict):
            continue
        typ = inc.get("type")
        iid = inc.get("id")
        if typ is not None and iid is not None:
            out[(str(typ), str(iid))] = inc
    return out


def _poster_from_jsonapi_relationships(
    item: dict[str, Any],
    included_index: dict[tuple[str, str], dict[str, Any]],
) -> Optional[str]:
    rel = item.get("relationships")
    if not isinstance(rel, dict):
        return None
    for rel_name in ("feature", "movie", "parent"):
        block = rel.get(rel_name)
        if not isinstance(block, dict):
            continue
        data = block.get("data")
        refs: list[dict[str, Any]] = []
        if isinstance(data, dict):
            refs = [data]
        elif isinstance(data, list):
            refs = [x for x in data if isinstance(x, dict)]
        for ref in refs:
            key = (str(ref.get("type", "")), str(ref.get("id", "")))
            inc = included_index.get(key)
            if not inc:
                continue
            iattr = inc.get("attributes")
            if not isinstance(iattr, dict):
                iattr = {}
            ifeat = iattr.get("feature_details")
            if not isinstance(ifeat, dict):
                ifeat = {}
            u = _poster_url_from_subtitle_attributes(iattr, ifeat)
            if u:
                return u
    return None


def resolve_poster_and_backdrop(
    item: dict[str, Any],
    attr: dict[str, Any],
    feat: dict[str, Any],
    included_index: dict[tuple[str, str], dict[str, Any]],
    tmdb_media_cache: dict[int, TmdbBundle],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
    """
    Resolve poster/backdrop from OpenSubtitles JSON, then TMDb by ``tmdb_id`` when
    ``TMDB_API_KEY`` is set. Also returns TMDb display title and release/air year
    for labeling rows when present.
    """
    poster_url = _poster_from_jsonapi_relationships(item, included_index)
    if not poster_url:
        poster_url = _poster_url_from_subtitle_attributes(attr, feat)
    if not poster_url:
        poster_url = _deep_find_image_url_in_payload(attr, feat)
    if poster_url:
        poster_url = _maybe_absolutize_opensubtitles_image_url(poster_url) or poster_url
    backdrop_url: Optional[str] = None
    tmdb_title: Optional[str] = None
    tmdb_year: Optional[int] = None
    tmdb_raw = feat.get("tmdb_id") or feat.get("parent_tmdb_id")
    if tmdb_raw is not None:
        bundle = tmdb_bundle_for_id(tmdb_raw, tmdb_media_cache)
        if not poster_url and bundle.poster:
            poster_url = bundle.poster
        if bundle.backdrop:
            backdrop_url = bundle.backdrop
        tmdb_title = bundle.display_title
        tmdb_year = bundle.display_year
    return poster_url, backdrop_url, tmdb_title, tmdb_year
