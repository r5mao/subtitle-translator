"""Display titles, years, and query filtering for OpenSubtitles rows and suggestions."""
from __future__ import annotations

import re
from typing import Any, Optional

_QUERY_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "or",
        "of",
        "a",
        "an",
        "in",
        "on",
        "at",
        "to",
        "for",
        "is",
        "it",
        "as",
    }
)


def title_is_placeholder(s: str) -> bool:
    """OpenSubtitles sometimes returns junk like 'Empty Movie (SubScene)' as title."""
    sl = (s or "").strip().lower()
    if not sl:
        return True
    if "empty movie" in sl:
        return True
    if "placeholder" in sl or "sample title" in sl:
        return True
    if "subscene" in sl and ("empty" in sl or "movie" in sl):
        return True
    return False


def release_looks_like_tech_strip_tag(s: str) -> bool:
    """Release string is often a rip label, not a human title."""
    rl = (s or "").strip().lower()
    if not rl:
        return False
    markers = (
        "subscene",
        "yify",
        "x264",
        "x265",
        "h264",
        "h265",
        "webrip",
        "bluray",
        "dvdrip",
        "1080p",
        "720p",
        "2160p",
        "hi10p",
        "remux",
        "proper",
        "repack",
    )
    return any(m in rl for m in markers)


def first_year_in_text(text: str) -> Optional[int]:
    """First standalone 19xx/20xx in arbitrary text (filename, movie_name, release)."""
    if not text:
        return None
    for m in re.finditer(r"(?<![0-9])(19\d{2}|20[0-3]\d)(?![0-9])", text):
        y = int(m.group(1))
        if 1950 <= y <= 2035:
            return y
    return None


def text_matches_search(blob: str, query: str) -> bool:
    """Match full query substring, significant tokens, or compact alphanumerics (for My.Mister vs mymister)."""
    ql = (query or "").strip().lower()
    if len(ql) < 2:
        return True
    if ql in blob:
        return True
    tokens = [t for t in re.split(r"[^\w]+", ql) if t]
    sig = [t for t in tokens if len(t) >= 4 or (len(t) >= 3 and t not in _QUERY_STOPWORDS)]
    if not sig:
        sig = tokens
    if sig and all(t in blob for t in sig):
        return True
    cq = re.sub(r"[^\w]", "", ql)
    cb = re.sub(r"[^\w]", "", blob)
    if len(cq) >= 4 and cq in cb:
        return True
    return False


def year_from_aligned_movie_name(feat: dict[str, Any], display_title: str) -> Optional[int]:
    """Use year embedded in movie_name only when that string plausibly describes the same work."""
    mn = str(feat.get("movie_name") or "").strip()
    if not mn:
        return None
    tl = (display_title or "").strip().lower()
    mnl = mn.lower()
    if tl:
        if tl not in mnl and mnl not in tl and not text_matches_search(mnl, tl):
            return None
    return first_year_in_text(mn)


def year_from_feature_air_dates(feat: dict[str, Any]) -> Optional[int]:
    for key in ("series_year", "parent_year", "season_year"):
        v = feat.get(key)
        if v is None:
            continue
        try:
            yi = int(v)
            if 1950 <= yi <= 2035:
                return yi
        except (TypeError, ValueError):
            continue
    for key in ("air_date", "first_air_date"):
        v = feat.get(key)
        if isinstance(v, str) and len(v) >= 4 and v[:4].isdigit():
            yi = int(v[:4])
            if 1950 <= yi <= 2035:
                return yi
    return None


def pick_display_year(
    feat: dict[str, Any],
    api_year: Any,
    file_name: str,
    rel_s: str,
    *,
    display_title: str = "",
) -> Any:
    """
    OpenSubtitles `feature_details.year` is often wrong (e.g. upload/catalog year). Prefer
    year from filename, then movie_name when it aligns with the row title (e.g. '2018 - My Mister'),
    then release, feature title text, air dates, then API year.
    """
    y = first_year_in_text(str(file_name or ""))
    if y is not None:
        return y
    y = year_from_aligned_movie_name(feat, display_title)
    if y is not None:
        return y
    y = first_year_in_text(str(rel_s or ""))
    if y is not None:
        return y
    y = first_year_in_text(str(feat.get("title") or ""))
    if y is not None:
        return y
    y = year_from_feature_air_dates(feat)
    if y is not None:
        return y
    return api_year


def title_hint_from_sub_filename(fname: str) -> str:
    """Best-effort show/movie name from typical subtitle filenames (e.g. My.Show.S01E01.x264)."""
    if not fname or not isinstance(fname, str):
        return ""
    stem = fname.rsplit(".", 1)[0] if "." in fname else fname
    tokens = re.split(r"[.\s_]+", stem)
    words: list[str] = []
    for t in tokens:
        if not t:
            continue
        if re.match(r"^[Ss]\d{1,2}([Ee]\d{1,2})?([Ee]\d{1,2})?$", t):
            break
        if re.match(r"^\d+[xX]\d+$", t):
            break
        if re.match(r"^\d{3,4}[pP]$", t, re.IGNORECASE):
            break
        if re.match(
            r"^(x264|x265|h264|h265|webrip|bluray|dvdrip|aac|dts|hdma|atmos)$",
            t,
            re.IGNORECASE,
        ):
            break
        if re.match(r"^\d{4}$", t) and words:
            break
        words.append(t)
    return " ".join(words) if words else ""


def looks_like_tv_feature(feat: dict[str, Any], attr: dict[str, Any]) -> bool:
    ft = str(feat.get("feature_type") or attr.get("feature_type") or "").strip().lower()
    if "episode" in ft or "tv" in ft or "series" in ft:
        return True
    if feat.get("season_number") is not None and feat.get("episode_number") is not None:
        return True
    return False


def primary_title_from_feature(feat: dict[str, Any], attr: dict[str, Any]) -> str:
    """
    Prefer stable names for display and dedupe. OpenSubtitles often stores a long
    'YEAR - Title' string in movie_name; title is usually cleaner. TV episodes may
    expose parent/series fields separate from episode title.
    """
    if not isinstance(feat, dict):
        feat = {}
    if not isinstance(attr, dict):
        attr = {}
    if looks_like_tv_feature(feat, attr):
        for key in (
            "parent_title",
            "parent_movie_name",
            "series_name",
            "series_title",
            "show_title",
            "tv_series_title",
        ):
            v = feat.get(key)
            if isinstance(v, str) and v.strip():
                base = v.strip()
                ep = feat.get("title")
                ep_s = ep.strip() if isinstance(ep, str) else ""
                if ep_s and ep_s.lower() != base.lower():
                    bl = base.lower()
                    el = ep_s.lower()
                    if not el.startswith(bl) and not bl.startswith(el):
                        merged = f"{base} · {ep_s}"
                        if not title_is_placeholder(merged):
                            return merged
                if not title_is_placeholder(base):
                    return base
    for key in ("original_title", "original_name", "original_movie_name"):
        v = feat.get(key)
        if isinstance(v, str) and v.strip() and not title_is_placeholder(v.strip()):
            return v.strip()
    t = feat.get("title")
    if isinstance(t, str) and t.strip() and not title_is_placeholder(t.strip()):
        return t.strip()
    mn = feat.get("movie_name")
    if isinstance(mn, str) and mn.strip() and not title_is_placeholder(mn.strip()):
        return mn.strip()
    return ""


def filter_subtitle_rows_by_query(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """
    Drop obvious off-topic hits when the user's query appears nowhere in title,
    release, or filename. If nothing would remain (e.g. non-Latin titles), keep all.
    """
    q = (query or "").strip().lower()
    if len(q) < 2:
        return rows

    def blob(r: dict[str, Any]) -> str:
        parts = [
            str(r.get("title") or ""),
            str(r.get("release") or ""),
            str(r.get("fileName") or ""),
        ]
        return " ".join(parts).lower()

    matched = [r for r in rows if text_matches_search(blob(r), query)]
    return matched if matched else rows


def filter_work_suggestions_by_query(suggestions: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Same idea as filter_subtitle_rows_by_query for distinct-work suggestions."""
    q = (query or "").strip()
    if len(q) < 2:
        return suggestions

    def blob(s: dict[str, Any]) -> str:
        return f"{s.get('title') or ''} {s.get('searchQuery') or ''}".lower()

    matched = [s for s in suggestions if text_matches_search(blob(s), q)]
    return matched if matched else suggestions


def clean_work_search_query(title: str, year: Any) -> str:
    """
    OpenSubtitles often uses movie_name like '1999 - The Matrix'. Appending (year) again
    breaks text search. Strip a leading 'YEAR -' and trailing '(YEAR)' when they match feature year.
    """
    t = (title or "").strip()
    if not t:
        return t
    ys = str(year).strip() if year is not None and year != "" else ""
    if ys.isdigit() and len(ys) == 4:
        t = re.sub(rf"^\s*{re.escape(ys)}\s*-\s*", "", t, flags=re.IGNORECASE).strip()
        t = re.sub(rf"\s*\(\s*{re.escape(ys)}\s*\)\s*$", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\s+", " ", t).strip()
    return t or (title or "").strip()
