import urllib.parse
import urllib.request
from typing import ClassVar, Dict

from srt_translator.services.opensubtitles_client import (
    OpenSubtitlesClient,
    OpenSubtitlesError,
    _maybe_absolutize_opensubtitles_image_url,
)


def test_poster_image_rejects_disallowed_host(client):
    bad = urllib.parse.quote("https://evil.example.com/poster.jpg", safe="")
    resp = client.get(f"/api/opensubtitles/poster-image?url={bad}")
    assert resp.status_code == 400
    err = (resp.get_json() or {}).get("error", "").lower()
    assert "host" in err or "not allowed" in err


def test_poster_image_requires_url(client):
    resp = client.get("/api/opensubtitles/poster-image")
    assert resp.status_code == 400


def test_poster_image_proxies_allowed_host(client, monkeypatch):
    class FakeResp:
        headers: ClassVar[Dict[str, str]] = {"Content-Type": "image/jpeg"}

        def read(self, n=65536):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return b"\xff\xd8\xff\xe0"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResp())
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_poster_proxy._POSTER_TIMEOUT_SEC",
        5,
    )

    u = urllib.parse.quote("https://s9.osdb.link/features/1/2/3/x.jpg", safe="")
    resp = client.get(f"/api/opensubtitles/poster-image?url={u}")
    assert resp.status_code == 200
    assert resp.data.startswith(b"\xff\xd8\xff")
    assert "image" in (resp.headers.get("Content-Type") or "").lower()


def test_poster_image_allows_amazon_imdb_style_host(client, monkeypatch):
    class FakeResp:
        headers: ClassVar[Dict[str, str]] = {"Content-Type": "image/jpeg"}

        def read(self, n=65536):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return b"\xff\xd8\xff\xe0"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResp())
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_poster_proxy._POSTER_TIMEOUT_SEC",
        5,
    )

    u = urllib.parse.quote("https://m.media-amazon.com/images/M/poster.jpg", safe="")
    resp = client.get(f"/api/opensubtitles/poster-image?url={u}")
    assert resp.status_code == 200


def test_maybe_absolutize_opensubtitles_poster_paths():
    """Site-relative poster paths must become absolute https URLs for the UI proxy."""
    assert (
        _maybe_absolutize_opensubtitles_image_url("/pictures/posters/x.jpg")
        == "https://www.opensubtitles.com/pictures/posters/x.jpg"
    )
    assert (
        _maybe_absolutize_opensubtitles_image_url("//img.example/a.png")
        == "https://img.example/a.png"
    )
    assert (
        _maybe_absolutize_opensubtitles_image_url("https://cdn.example/z.webp")
        == "https://cdn.example/z.webp"
    )
    assert _maybe_absolutize_opensubtitles_image_url("/pictures/../evil.jpg") is None


def test_poster_image_proxy_query_url_construction_roundtrip():
    """Mirrors static/js/opensubtitles-format.js posterProxySrc: path must decode back to the remote poster URL."""
    api_base = "http://127.0.0.1:5555"
    remote = "https://s9.osdb.link/features/1/2/3/poster.jpg?token=x&raw=1"
    q = urllib.parse.quote(remote, safe="")
    proxy = f"{api_base.rstrip('/')}/api/opensubtitles/poster-image?url={q}"
    parsed = urllib.parse.urlparse(proxy)
    qs = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
    assert urllib.parse.unquote(qs["url"][0]) == remote


def test_poster_image_allows_cloudfront(client, monkeypatch):
    class FakeResp:
        headers: ClassVar[Dict[str, str]] = {"Content-Type": "image/jpeg"}

        def read(self, n=65536):
            if getattr(self, "_done", False):
                return b""
            self._done = True
            return b"\xff\xd8\xff"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResp())
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_poster_proxy._POSTER_TIMEOUT_SEC",
        5,
    )

    u = urllib.parse.quote(
        "https://d111111abcdef8.cloudfront.net/out/poster.jpg", safe=""
    )
    resp = client.get(f"/api/opensubtitles/poster-image?url={u}")
    assert resp.status_code == 200
    assert resp.data.startswith(b"\xff\xd8\xff")


def test_subtitles_search_retries_without_include_on_400(monkeypatch):
    calls: list[tuple] = []

    def fake_request(
        self, method, path, *, query=None, json_body=None, retry_login=True
    ):
        calls.append((method, path, dict(query or {})))
        if len(calls) == 1:
            raise OpenSubtitlesError("OpenSubtitles request failed (400): bad request")
        return {"data": []}

    monkeypatch.setattr(OpenSubtitlesClient, "login", lambda self, force=False: None)
    monkeypatch.setattr(OpenSubtitlesClient, "_request", fake_request)
    c = OpenSubtitlesClient(api_key="k", username="u", password="p")
    out = c.search("matrix", page=1, per_page=10)
    assert out == {"data": []}
    assert len(calls) == 2
    assert calls[0][2].get("include") == "feature"
    assert "include" not in calls[1][2]
