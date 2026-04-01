"""OpenSubtitles.com REST API v1 client (server-side only)."""
from __future__ import annotations

import gzip
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Filled from GET /api/v1/infos/languages (code -> display name)
_subtitle_language_names_cache: Optional[dict[str, str]] = None

DEFAULT_API_ROOT = "https://api.opensubtitles.com"
DEFAULT_USER_AGENT = os.environ.get("OPENSUBTITLES_USER_AGENT", "SubtitleTranslatorApp 1.0")


def _https_base(host: str) -> str:
    h = (host or "api.opensubtitles.com").strip().rstrip("/")
    if h.startswith("http://"):
        h = h[len("http://") :]
    elif h.startswith("https://"):
        h = h[len("https://") :]
    return f"https://{h}"


class OpenSubtitlesError(Exception):
    """API or network error."""


class OpenSubtitlesNotConfigured(OpenSubtitlesError):
    """Missing API credentials."""


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


class OpenSubtitlesClient:
    """Login, search subtitles, download bytes. Token refreshed on 401."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        user_agent: Optional[str] = None,
        urlopen: Optional[Callable[..., Any]] = None,
    ):
        self.api_key = (api_key or os.environ.get("OPENSUBTITLES_API_KEY") or "").strip()
        self.username = (username or os.environ.get("OPENSUBTITLES_USERNAME") or "").strip()
        self.password = (password or os.environ.get("OPENSUBTITLES_PASSWORD") or "").strip()
        self.user_agent = (user_agent or DEFAULT_USER_AGENT).strip()
        self._urlopen = urlopen or urllib.request.urlopen
        self._base_url = _https_base("api.opensubtitles.com")
        self._token: Optional[str] = None
        self._login_at: float = 0.0

    def configured(self) -> bool:
        return bool(self.api_key and self.username and self.password)

    def _require_config(self) -> None:
        if not self.configured():
            raise OpenSubtitlesNotConfigured(
                "OpenSubtitles is not configured on this server (missing API key or credentials)."
            )

    def _headers(self, json_body: bool = False) -> dict[str, str]:
        h = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if json_body:
            h["Content-Type"] = "application/json"
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[dict[str, str]] = None,
        json_body: Optional[dict] = None,
        retry_login: bool = True,
    ) -> dict[str, Any]:
        self._require_config()
        qs = f"?{urllib.parse.urlencode(query)}" if query else ""
        url = f"{self._base_url}{path}{qs}"
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(json_body=json_body is not None), method=method)
        try:
            with self._urlopen(req, timeout=60) as resp:
                raw = resp.read()
                encoding = resp.headers.get_content_charset() or "utf-8"
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                raise OpenSubtitlesError(
                    "OpenSubtitles rate limit reached — wait a moment and try again, or upload a file."
                ) from e
            if e.code == 401 and retry_login:
                self._token = None
                self.login(force=True)
                return self._request(method, path, query=query, json_body=json_body, retry_login=False)
            logger.warning("OpenSubtitles HTTP %s: %s", e.code, body[:500])
            raise OpenSubtitlesError(f"OpenSubtitles request failed ({e.code}): {body[:200]}") from e
        except urllib.error.URLError as e:
            raise OpenSubtitlesError(f"OpenSubtitles network error: {e}") from e

        try:
            return json.loads(raw.decode(encoding))
        except json.JSONDecodeError as e:
            raise OpenSubtitlesError("Invalid JSON from OpenSubtitles") from e

    def login(self, force: bool = False) -> None:
        self._require_config()
        if self._token and not force and (time.monotonic() - self._login_at) < 3600:
            return
        payload = {"username": self.username, "password": self.password}
        url = f"{DEFAULT_API_ROOT}/api/v1/login"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(json_body=True),
            method="POST",
        )
        try:
            with self._urlopen(req, timeout=30) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise OpenSubtitlesError(f"OpenSubtitles login failed ({e.code}): {body[:300]}") from e
        except urllib.error.URLError as e:
            raise OpenSubtitlesError(f"OpenSubtitles login network error: {e}") from e

        token = parsed.get("token")
        if not token:
            raise OpenSubtitlesError("OpenSubtitles login did not return a token")
        self._token = token
        self._login_at = time.monotonic()
        base = parsed.get("base_url") or "api.opensubtitles.com"
        self._base_url = _https_base(str(base))
        logger.info("OpenSubtitles login OK, base_url=%s", self._base_url)

    def fetch_language_names(self) -> dict[str, str]:
        """Map OpenSubtitles language_code -> human-readable name (GET /infos/languages)."""
        payload = self._request("GET", "/api/v1/infos/languages")
        return _parse_language_infos_payload(payload)

    def search(
        self,
        query: str,
        *,
        languages: str = "",
        page: int = 1,
        per_page: int = 10,
        year: Optional[int] = None,
        imdb_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Search subtitles. `languages` is comma-separated OS codes; empty = any language."""
        self.login()
        q: dict[str, str] = {
            "query": query.strip(),
            "page": str(max(1, page)),
            "per_page": str(max(1, min(100, int(per_page)))),
            # JSON:API-style sideload so poster/image fields may appear on `included` resources.
            "include": "feature",
        }
        if languages.strip():
            q["languages"] = languages.strip()
        if year is not None:
            try:
                yi = int(year)
                if 1870 <= yi <= 2100:
                    q["year"] = str(yi)
            except (TypeError, ValueError):
                pass
        nimdb = normalize_opensubtitles_imdb_id(imdb_id)
        if nimdb:
            q["imdb_id"] = nimdb
        try:
            return self._request("GET", "/api/v1/subtitles", query=q)
        except OpenSubtitlesError as e:
            if " (400)" in str(e) and q.get("include"):
                logger.warning(
                    "OpenSubtitles GET /subtitles returned 400 with include=%s; retrying without include",
                    q.get("include"),
                )
                q2 = {k: v for k, v in q.items() if k != "include"}
                return self._request("GET", "/api/v1/subtitles", query=q2)
            raise

    def request_download_link(self, file_id: str) -> tuple[str, str]:
        """Return (download_url, suggested_file_name)."""
        self.login()
        try:
            fid = int(file_id)
        except ValueError:
            fid = file_id
        body = self._request("POST", "/api/v1/download", json_body={"file_id": fid})
        link = body.get("link")
        fname = body.get("file_name") or body.get("filename")
        if not link and isinstance(body.get("data"), dict):
            data = body["data"]
            link = data.get("link") or data.get("url")
            fname = fname or data.get("file_name") or data.get("filename")
        if not link:
            raise OpenSubtitlesError("OpenSubtitles download response missing link")
        return str(link), str(fname or "subtitle.srt")

    def download_file(self, file_id: str) -> tuple[bytes, str]:
        """Resolve download link and return (raw bytes, filename)."""
        link, fname = self.request_download_link(file_id)
        req = urllib.request.Request(link, headers={"User-Agent": self.user_agent, "Accept": "*/*"})
        try:
            with self._urlopen(req, timeout=120) as resp:
                raw = resp.read()
                enc = resp.headers.get("Content-Encoding", "").lower()
        except urllib.error.URLError as e:
            raise OpenSubtitlesError(f"Download failed: {e}") from e
        if enc == "gzip" or (len(raw) > 2 and raw[:2] == b"\x1f\x8b"):
            try:
                raw = gzip.decompress(raw)
            except OSError:
                try:
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                except OSError as e:
                    raise OpenSubtitlesError("Could not decompress subtitle archive") from e
        return raw, fname


def reset_subtitle_language_names_cache() -> None:
    """Clear cached language table (for tests)."""
    global _subtitle_language_names_cache
    _subtitle_language_names_cache = None


def _parse_language_infos_payload(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    items = data.get("data")
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        attrs = item.get("attributes")
        if isinstance(attrs, dict):
            code = attrs.get("language_code") or attrs.get("code")
            name = attrs.get("language_name") or attrs.get("name")
        else:
            code = item.get("language_code")
            name = item.get("language_name")
        if code and name:
            out[str(code).strip()] = str(name).strip()
    return out


def get_language_name_lookup(client: OpenSubtitlesClient) -> dict[str, str]:
    """Return cached OpenSubtitles language code -> display name map."""
    global _subtitle_language_names_cache
    if _subtitle_language_names_cache is not None:
        return _subtitle_language_names_cache
    client.login()
    try:
        _subtitle_language_names_cache = client.fetch_language_names()
    except OpenSubtitlesError as e:
        logger.warning("Could not load OpenSubtitles language names: %s", e)
        _subtitle_language_names_cache = {}
    return _subtitle_language_names_cache


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


def _tmdb_first_poster_from_images_payload(payload: Any) -> Optional[str]:
    posters = payload.get("posters") if isinstance(payload, dict) else None
    if isinstance(posters, list) and posters:
        fp = posters[0].get("file_path") if isinstance(posters[0], dict) else None
        if isinstance(fp, str) and fp.startswith("/"):
            return f"https://image.tmdb.org/t/p/w185{fp}"
    return None


def _tmdb_first_backdrop_from_images_payload(payload: Any) -> Optional[str]:
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


def _tmdb_fetch_images_payload(tid: int, kind: str, api_key: str) -> Optional[dict[str, Any]]:
    qs = urllib.parse.urlencode({"api_key": api_key})
    url = f"https://api.themoviedb.org/3/{kind}/{tid}/images?{qs}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT},
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


def _tmdb_poster_and_backdrop_for_id(
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
        payload = _tmdb_fetch_images_payload(tid, kind, api_key)
        if not payload:
            continue
        poster = _tmdb_first_poster_from_images_payload(payload)
        backdrop = _tmdb_first_backdrop_from_images_payload(payload)
        if poster or backdrop:
            cache[tid] = (poster, backdrop)
            return cache[tid]
    cache[tid] = (None, None)
    return (None, None)


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


def _included_resource_index(included: Any) -> dict[tuple[str, str], dict[str, Any]]:
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


def _resolve_poster_and_backdrop(
    item: dict[str, Any],
    attr: dict[str, Any],
    feat: dict[str, Any],
    included_index: dict[tuple[str, str], dict[str, Any]],
    tmdb_media_cache: dict[int, tuple[Optional[str], Optional[str]]],
) -> tuple[Optional[str], Optional[str]]:
    poster_url = _poster_from_jsonapi_relationships(item, included_index)
    if not poster_url:
        poster_url = _poster_url_from_subtitle_attributes(attr, feat)
    if not poster_url:
        poster_url = _deep_find_image_url_in_payload(attr, feat)
    if poster_url:
        poster_url = _maybe_absolutize_opensubtitles_image_url(poster_url) or poster_url
    backdrop_url: Optional[str] = None
    tmdb_raw = feat.get("tmdb_id") or feat.get("parent_tmdb_id")
    if tmdb_raw is not None:
        tmdb_poster, tmdb_backdrop = _tmdb_poster_and_backdrop_for_id(tmdb_raw, tmdb_media_cache)
        if not poster_url and tmdb_poster:
            poster_url = tmdb_poster
        if tmdb_backdrop:
            backdrop_url = tmdb_backdrop
    return poster_url, backdrop_url


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


def _title_is_placeholder(s: str) -> bool:
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


def _release_looks_like_tech_strip_tag(s: str) -> bool:
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


def _first_year_in_text(text: str) -> Optional[int]:
    """First standalone 19xx/20xx in arbitrary text (filename, movie_name, release)."""
    if not text:
        return None
    for m in re.finditer(r"(?<![0-9])(19\d{2}|20[0-3]\d)(?![0-9])", text):
        y = int(m.group(1))
        if 1950 <= y <= 2035:
            return y
    return None


def _year_from_aligned_movie_name(feat: dict[str, Any], display_title: str) -> Optional[int]:
    """Use year embedded in movie_name only when that string plausibly describes the same work."""
    mn = str(feat.get("movie_name") or "").strip()
    if not mn:
        return None
    tl = (display_title or "").strip().lower()
    mnl = mn.lower()
    if tl:
        if tl not in mnl and mnl not in tl and not _text_matches_search(mnl, tl):
            return None
    return _first_year_in_text(mn)


def _year_from_feature_air_dates(feat: dict[str, Any]) -> Optional[int]:
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


def _pick_display_year(
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
    result: Any
    src: str
    y = _first_year_in_text(str(file_name or ""))
    if y is not None:
        result, src = y, "filename"
    else:
        y = _year_from_aligned_movie_name(feat, display_title)
        if y is not None:
            result, src = y, "movie_name"
        else:
            y = _first_year_in_text(str(rel_s or ""))
            if y is not None:
                result, src = y, "release"
            else:
                y = _first_year_in_text(str(feat.get("title") or ""))
                if y is not None:
                    result, src = y, "title"
                else:
                    y = _year_from_feature_air_dates(feat)
                    if y is not None:
                        result, src = y, "air_dates"
                    else:
                        result, src = api_year, "api"
    # #region agent log
    try:
        import json
        import time

        with open("debug-567c23.log", "a", encoding="utf-8") as _df:
            _df.write(
                json.dumps(
                    {
                        "sessionId": "567c23",
                        "hypothesisId": "H1",
                        "location": "opensubtitles_client._pick_display_year",
                        "message": "display_year_resolution",
                        "data": {
                            "source": src,
                            "resolved": result,
                            "api_year": api_year,
                            "display_title_preview": str(display_title or "")[:80],
                            "movie_name_preview": str(feat.get("movie_name") or "")[:120],
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion
    return result


def _title_hint_from_sub_filename(fname: str) -> str:
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


def _text_matches_search(blob: str, query: str) -> bool:
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


def _looks_like_tv_feature(feat: dict[str, Any], attr: dict[str, Any]) -> bool:
    ft = str(feat.get("feature_type") or attr.get("feature_type") or "").strip().lower()
    if "episode" in ft or "tv" in ft or "series" in ft:
        return True
    if feat.get("season_number") is not None and feat.get("episode_number") is not None:
        return True
    return False


def _primary_title_from_feature(feat: dict[str, Any], attr: dict[str, Any]) -> str:
    """
    Prefer stable names for display and dedupe. OpenSubtitles often stores a long
    'YEAR - Title' string in movie_name; title is usually cleaner. TV episodes may
    expose parent/series fields separate from episode title.
    """
    if not isinstance(feat, dict):
        feat = {}
    if not isinstance(attr, dict):
        attr = {}
    if _looks_like_tv_feature(feat, attr):
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
                        if not _title_is_placeholder(merged):
                            return merged
                if not _title_is_placeholder(base):
                    return base
    for key in ("original_title", "original_name", "original_movie_name"):
        v = feat.get(key)
        if isinstance(v, str) and v.strip() and not _title_is_placeholder(v.strip()):
            return v.strip()
    t = feat.get("title")
    if isinstance(t, str) and t.strip() and not _title_is_placeholder(t.strip()):
        return t.strip()
    mn = feat.get("movie_name")
    if isinstance(mn, str) and mn.strip() and not _title_is_placeholder(mn.strip()):
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

    matched = [r for r in rows if _text_matches_search(blob(r), query)]
    return matched if matched else rows


def filter_work_suggestions_by_query(suggestions: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Same idea as filter_subtitle_rows_by_query for distinct-work suggestions."""
    q = (query or "").strip()
    if len(q) < 2:
        return suggestions

    def blob(s: dict[str, Any]) -> str:
        return f"{s.get('title') or ''} {s.get('searchQuery') or ''}".lower()

    matched = [s for s in suggestions if _text_matches_search(blob(s), q)]
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
    title = _primary_title_from_feature(feat, attr) or str(attr.get("release") or "").strip()
    year = feat.get("year")
    season = feat.get("season_number")
    episode = feat.get("episode_number")
    return f"fallback:{title}|{year}|{season}|{episode}"


def _work_suggestion_from_subtitle_item(
    item: dict[str, Any],
    included_index: dict[tuple[str, str], dict[str, Any]],
    tmdb_media_cache: dict[int, tuple[Optional[str], Optional[str]]],
) -> Optional[dict[str, Any]]:
    attr = item.get("attributes") or {}
    if not isinstance(attr, dict):
        attr = {}
    feat = attr.get("feature_details") or {}
    if not isinstance(feat, dict):
        feat = {}
    title = _primary_title_from_feature(feat, attr)
    if _title_is_placeholder(title):
        title = ""
    if not title:
        files = attr.get("files")
        if isinstance(files, list) and files and isinstance(files[0], dict):
            title = _title_hint_from_sub_filename(str(files[0].get("file_name") or ""))
    if not title:
        rel_s = str(attr.get("release") or "").strip()
        if rel_s and not _release_looks_like_tech_strip_tag(rel_s):
            title = rel_s
    if not title:
        return None
    rel_s = str(attr.get("release") or "").strip()
    fn0 = ""
    _files = attr.get("files")
    if isinstance(_files, list) and _files and isinstance(_files[0], dict):
        fn0 = str(_files[0].get("file_name") or "")
    api_year = feat.get("year")
    year = _pick_display_year(feat, api_year, fn0, rel_s, display_title=title)
    season = feat.get("season_number")
    episode = feat.get("episode_number")
    feature_type = feat.get("feature_type") or attr.get("feature_type")
    poster_url, _bd = _resolve_poster_and_backdrop(item, attr, feat, included_index, tmdb_media_cache)

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

    seen: dict[str, dict[str, Any]] = {}
    key_order: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = _feature_dedupe_key(item)
        if key not in seen:
            seen[key] = item
            key_order.append(key)

    included_index = _included_resource_index(api_json.get("included"))
    tmdb_media_cache: dict[int, tuple[Optional[str], Optional[str]]] = {}
    out: list[dict[str, Any]] = []
    for key in key_order:
        if len(out) >= cap:
            break
        sug = _work_suggestion_from_subtitle_item(seen[key], included_index, tmdb_media_cache)
        if sug:
            out.append(sug)
    return out


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

    included_index = _included_resource_index(api_json.get("included"))
    tmdb_media_cache: dict[int, tuple[Optional[str], Optional[str]]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        attr = item.get("attributes") or {}
        if not isinstance(attr, dict):
            attr = {}
        feat = attr.get("feature_details") or {}
        if not isinstance(feat, dict):
            feat = {}

        base_feature_title = _primary_title_from_feature(feat, attr)
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
            # Single-file payloads sometimes expose file_id on attributes
            fid = attr.get("file_id") or attr.get("files_file_id")
            if fid is not None:
                _stub = (base_feature_title or "subtitle") if not _title_is_placeholder(base_feature_title) else "subtitle"
                files = [{"file_id": fid, "file_name": attr.get("file_name") or release or f"{_stub}.{language}.srt"}]
            else:
                continue

        poster_url, backdrop_url = _resolve_poster_and_backdrop(
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
                        (language_names[k] for k in language_names if k.lower() == lc.lower()),
                        lc,
                    )
                )
            row_title = base_feature_title
            if _title_is_placeholder(row_title):
                row_title = ""
            if not row_title:
                row_title = _title_hint_from_sub_filename(str(file_name))
            rel_s = str(release or "").strip()
            if not row_title and rel_s and not _release_looks_like_tech_strip_tag(rel_s):
                row_title = rel_s
            if not row_title:
                row_title = str(file_name) if file_name else "—"
            fn_s = str(file_name)
            display_year = _pick_display_year(feat, year, fn_s, rel_s, display_title=row_title)
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
