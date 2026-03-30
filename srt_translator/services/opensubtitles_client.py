"""OpenSubtitles.com REST API v1 client (server-side only)."""
from __future__ import annotations

import gzip
import io
import json
import logging
import os
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
        per_page: int = 25,
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
        return self._request("GET", "/api/v1/subtitles", query=q)

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
    return False


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
            u = _normalize_media_url(rl.get(key))
            if u:
                return u
        for v in rl.values():
            u = _normalize_media_url(v)
            if u and _looks_like_image_url(u):
                return u
    if isinstance(rl, list):
        for item in rl:
            if isinstance(item, dict):
                for key in ("img_url", "image_url", "imgUrl", "imageUrl"):
                    u = _normalize_media_url(item.get(key))
                    if u:
                        return u
                u = _normalize_media_url(item.get("url"))
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
            u = _normalize_media_url(src.get(key))
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

    for item in items:
        if not isinstance(item, dict):
            continue
        attr = item.get("attributes") or {}
        if not isinstance(attr, dict):
            attr = {}
        feat = attr.get("feature_details") or {}
        if not isinstance(feat, dict):
            feat = {}

        title = feat.get("movie_name") or feat.get("title") or attr.get("release") or ""
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
                files = [{"file_id": fid, "file_name": attr.get("file_name") or release or f"{title}.{language}.srt"}]
            else:
                continue

        poster_url = _poster_from_jsonapi_relationships(item, included_index)
        if not poster_url:
            poster_url = _poster_url_from_subtitle_attributes(attr, feat)

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
            rows.append(
                {
                    "fileId": str(fid),
                    "title": str(title) if title else release or file_name,
                    "year": year,
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
