from srt_translator.services.opensubtitles_client import normalize_opensubtitles_imdb_id

from tests.opensubtitles.support import FakeOpenSubtitlesClient, FakeOpenSubtitlesManyPages


class FakeRefineEmptyThenBroad(FakeOpenSubtitlesClient):
    """First refined search returns no rows; broad search (no year/imdb) returns hits."""

    def __init__(self):
        super().__init__()
        self._search_calls = 0

    def search(self, query, languages="", page=1, per_page=10, *, year=None, imdb_id=None, **kwargs):
        self._search_calls += 1
        type(self).last_search = {
            "query": query,
            "languages": languages,
            "page": page,
            "per_page": per_page,
            "year": year,
            "imdb_id": imdb_id,
        }
        if self._search_calls == 1 and (year is not None or imdb_id):
            return {"data": [], "total_pages": 1, "total_count": 0}
        return super().search(
            query,
            languages=languages,
            page=page,
            per_page=per_page,
            year=year,
            imdb_id=imdb_id,
            **kwargs,
        )


def test_opensubtitles_status_unconfigured(client, monkeypatch):
    monkeypatch.delenv("OPENSUBTITLES_API_KEY", raising=False)
    monkeypatch.delenv("OPENSUBTITLES_USERNAME", raising=False)
    monkeypatch.delenv("OPENSUBTITLES_PASSWORD", raising=False)
    resp = client.get("/api/opensubtitles/status")
    assert resp.status_code == 200
    assert resp.get_json()["configured"] is False


def test_opensubtitles_search_503_without_credentials(client, monkeypatch):
    monkeypatch.delenv("OPENSUBTITLES_API_KEY", raising=False)
    monkeypatch.delenv("OPENSUBTITLES_USERNAME", raising=False)
    monkeypatch.delenv("OPENSUBTITLES_PASSWORD", raising=False)
    resp = client.post("/api/opensubtitles/search", json={"query": "matrix"})
    assert resp.status_code == 503
    assert "not configured" in resp.get_json()["error"].lower()


def test_opensubtitles_search_returns_results(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.get_language_name_lookup",
        lambda _c: {"en": "English"},
    )
    resp = client.post(
        "/api/opensubtitles/search",
        json={"query": "Test Movie", "language": "en", "page": 1},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["results"]) >= 1
    row = data["results"][0]
    assert row["fileId"] == "999001"
    assert row["language"] == "en"
    assert row["languageName"] == "English"
    assert row["title"] == "Test Movie"
    assert row["posterUrl"] == "https://example.com/poster/test-movie.jpg"
    assert data["page"] == 1
    assert data["perPage"] == 10
    assert data["totalPages"] == 3
    assert data["totalCount"] == 75
    assert FakeOpenSubtitlesClient.last_search["per_page"] == 10


def test_opensubtitles_search_caps_total_pages(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesManyPages,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.get_language_name_lookup",
        lambda _c: {"en": "English"},
    )
    resp = client.post(
        "/api/opensubtitles/search",
        json={"query": "Test Movie", "language": "en", "page": 1},
    )
    assert resp.status_code == 200
    assert resp.get_json()["totalPages"] == 10


def test_opensubtitles_search_rejects_page_above_cap(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.get_language_name_lookup",
        lambda _c: {"en": "English"},
    )
    resp = client.post(
        "/api/opensubtitles/search",
        json={"query": "Test Movie", "language": "en", "page": 11},
    )
    assert resp.status_code == 400


def test_opensubtitles_search_accepts_per_page(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.get_language_name_lookup",
        lambda _c: {"en": "English"},
    )
    resp = client.post(
        "/api/opensubtitles/search",
        json={"query": "Test Movie", "language": "en", "page": 2, "perPage": 50},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["page"] == 2
    assert data["perPage"] == 50
    assert FakeOpenSubtitlesClient.last_search["page"] == 2
    assert FakeOpenSubtitlesClient.last_search["per_page"] == 50


def test_normalize_opensubtitles_imdb_id():
    assert normalize_opensubtitles_imdb_id("tt0133093") == "0133093"
    assert normalize_opensubtitles_imdb_id(1330933) == "1330933"
    assert normalize_opensubtitles_imdb_id("bad") is None


def test_opensubtitles_search_refine_fallback_when_refined_empty(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeRefineEmptyThenBroad,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.get_language_name_lookup",
        lambda _c: {"en": "English"},
    )
    resp = client.post(
        "/api/opensubtitles/search",
        json={
            "query": "Test Movie",
            "language": "en",
            "page": 1,
            "year": 2020,
            "imdbId": "tt1234567",
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["results"]) >= 1
    assert FakeRefineEmptyThenBroad.last_search["year"] is None
    assert FakeRefineEmptyThenBroad.last_search["imdb_id"] is None


def test_opensubtitles_search_passes_year_and_imdb_to_client(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.get_language_name_lookup",
        lambda _c: {"en": "English"},
    )
    resp = client.post(
        "/api/opensubtitles/search",
        json={
            "query": "The Matrix",
            "language": "en",
            "page": 1,
            "year": 1999,
            "imdbId": "tt0133093",
        },
    )
    assert resp.status_code == 200
    assert FakeOpenSubtitlesClient.last_search["year"] == 1999
    assert FakeOpenSubtitlesClient.last_search["imdb_id"] == "0133093"


def test_opensubtitles_search_ignores_out_of_range_year(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.get_language_name_lookup",
        lambda _c: {"en": "English"},
    )
    resp = client.post(
        "/api/opensubtitles/search",
        json={"query": "Test Movie", "language": "en", "year": 1700},
    )
    assert resp.status_code == 200
    assert FakeOpenSubtitlesClient.last_search.get("year") is None
