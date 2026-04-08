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

from srt_translator.services.opensubtitles_ids import normalize_opensubtitles_imdb_id

logger = logging.getLogger(__name__)

# Filled from GET /api/v1/infos/languages (code -> display name)
_subtitle_language_names_cache: Optional[dict[str, str]] = None

DEFAULT_API_ROOT = "https://api.opensubtitles.com"
DEFAULT_USER_AGENT = os.environ.get(
    "OPENSUBTITLES_USER_AGENT", "SubtitleTranslatorApp 1.0"
)


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
        self.api_key = (
            api_key or os.environ.get("OPENSUBTITLES_API_KEY") or ""
        ).strip()
        self.username = (
            username or os.environ.get("OPENSUBTITLES_USERNAME") or ""
        ).strip()
        self.password = (
            password or os.environ.get("OPENSUBTITLES_PASSWORD") or ""
        ).strip()
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
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(json_body=json_body is not None),
            method=method,
        )
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
                return self._request(
                    method, path, query=query, json_body=json_body, retry_login=False
                )
            logger.warning("OpenSubtitles HTTP %s: %s", e.code, body[:500])
            raise OpenSubtitlesError(
                f"OpenSubtitles request failed ({e.code}): {body[:200]}"
            ) from e
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
            raise OpenSubtitlesError(
                f"OpenSubtitles login failed ({e.code}): {body[:300]}"
            ) from e
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
        req = urllib.request.Request(
            link, headers={"User-Agent": self.user_agent, "Accept": "*/*"}
        )
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
                    raise OpenSubtitlesError(
                        "Could not decompress subtitle archive"
                    ) from e
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


from srt_translator.services.opensubtitles_results import (  # noqa: E402
    _maybe_absolutize_opensubtitles_image_url,
    clean_work_search_query,
    distinct_work_suggestions_from_subtitles,
    filter_subtitle_rows_by_query,
    filter_work_suggestions_by_query,
    flatten_subtitle_results,
    total_count_from_response,
    total_pages_from_response,
)

__all__ = [
    "DEFAULT_API_ROOT",
    "DEFAULT_USER_AGENT",
    "OpenSubtitlesClient",
    "OpenSubtitlesError",
    "OpenSubtitlesNotConfigured",
    "_maybe_absolutize_opensubtitles_image_url",
    "clean_work_search_query",
    "distinct_work_suggestions_from_subtitles",
    "filter_subtitle_rows_by_query",
    "filter_work_suggestions_by_query",
    "flatten_subtitle_results",
    "get_language_name_lookup",
    "normalize_opensubtitles_imdb_id",
    "reset_subtitle_language_names_cache",
    "total_count_from_response",
    "total_pages_from_response",
]
