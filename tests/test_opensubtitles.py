import os
import tempfile
import uuid

import pytest

from srt_translator.services.opensubtitles_client import reset_subtitle_language_names_cache
from tests.test_translate_and_download import make_srt


@pytest.fixture(autouse=True)
def _reset_os_language_cache():
    reset_subtitle_language_names_cache()
    yield
    reset_subtitle_language_names_cache()


class _FakeOpenSubtitlesClient:
    """Stub for OpenSubtitlesClient in route tests."""

    last_search = None

    def __init__(self):
        pass

    def configured(self):
        return True

    def search(self, query, languages="", page=1, per_page=25):
        assert query.strip()
        type(self).last_search = {
            "query": query,
            "languages": languages,
            "page": page,
            "per_page": per_page,
        }
        return {
            "data": [
                {
                    "type": "subtitle",
                    "attributes": {
                        "language": "en",
                        "release": "Test.Release",
                        "download_count": 42,
                        "fps": 23.976,
                        "files": [{"file_id": 999001, "file_name": "sample_en.srt"}],
                        "feature_details": {"movie_name": "Test Movie", "year": 2020},
                        "related_links": {
                            "img_url": "https://example.com/poster/test-movie.jpg",
                        },
                    },
                }
            ],
            "total_pages": 3,
            "total_count": 75,
        }

    def download_file(self, file_id):
        return make_srt(), "sample_en.srt"


@pytest.fixture
def os_env_configured(monkeypatch):
    monkeypatch.setenv("OPENSUBTITLES_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENSUBTITLES_USERNAME", "test-user")
    monkeypatch.setenv("OPENSUBTITLES_PASSWORD", "test-pass")


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
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeOpenSubtitlesClient,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.get_language_name_lookup",
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
    assert data["perPage"] == 25
    assert data["totalPages"] == 3
    assert data["totalCount"] == 75
    assert _FakeOpenSubtitlesClient.last_search["per_page"] == 25


def test_opensubtitles_search_accepts_per_page(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeOpenSubtitlesClient,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.get_language_name_lookup",
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
    assert _FakeOpenSubtitlesClient.last_search["page"] == 2
    assert _FakeOpenSubtitlesClient.last_search["per_page"] == 50


def test_opensubtitles_fetch_stores_temp_file(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeOpenSubtitlesClient,
    )
    resp = client.post("/api/opensubtitles/fetch", json={"file_id": "999001"})
    assert resp.status_code == 200
    j = resp.get_json()
    assert "fetchedId" in j
    assert j["filename"].endswith(".srt")
    fid = j["fetchedId"]
    temp_dir = tempfile.gettempdir()
    matches = [f for f in os.listdir(temp_dir) if f.startswith(f"{fid}_")]
    assert len(matches) == 1
    path = os.path.join(temp_dir, matches[0])
    os.remove(path)


def test_translate_with_fetched_id(client, patch_translator, monkeypatch):
    monkeypatch.delenv("OPENSUBTITLES_API_KEY", raising=False)
    fetched_id = str(uuid.uuid4())
    temp_dir = tempfile.gettempdir()
    name = f"{fetched_id}_remote_en.srt"
    path = os.path.join(temp_dir, name)
    with open(path, "wb") as f:
        f.write(make_srt())
    try:
        resp = client.post(
            "/api/translate",
            data={
                "sourceLanguage": "en",
                "targetLanguage": "zh-cn",
                "dualLanguage": "false",
                "taskId": str(uuid.uuid4()),
                "fetchedId": fetched_id,
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        j = resp.get_json()
        assert j["success"] is True
        assert not os.path.exists(path), "fetched temp file should be removed after translate"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_translate_rejects_bad_fetched_id(client, patch_translator):
    resp = client.post(
        "/api/translate",
        data={
            "sourceLanguage": "en",
            "targetLanguage": "zh-cn",
            "dualLanguage": "false",
            "taskId": str(uuid.uuid4()),
            "fetchedId": str(uuid.uuid4()),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 404


def test_ui_lang_mapping_pt_covers_both_variants():
    from srt_translator.services.opensubtitles_lang import ui_lang_to_opensubtitles

    assert "pt-pt" in ui_lang_to_opensubtitles("pt")
    assert "pt-br" in ui_lang_to_opensubtitles("pt")


def test_ui_pinyin_maps_to_base_zh_for_search():
    from srt_translator.services.opensubtitles_lang import ui_lang_to_opensubtitles

    assert ui_lang_to_opensubtitles("zh-cn-pinyin") == "zh-cn"


def test_flatten_subtitle_results_language_name():
    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "fr",
                    "files": [{"file_id": 1, "file_name": "x.srt"}],
                    "feature_details": {"movie_name": "M"},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload, language_names={"fr": "French"})
    assert len(rows) == 1
    assert rows[0]["language"] == "fr"
    assert rows[0]["languageName"] == "French"


def test_flatten_poster_related_links_list():
    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "related_links": [
                        {
                            "label": "Movie",
                            "url": "https://www.opensubtitles.com/en/movies/x",
                            "img_url": "https://s9.osdb.link/features/1/2/3/99.jpg",
                        },
                    ],
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://s9.osdb.link/features/1/2/3/99.jpg"


def test_flatten_poster_from_included_feature():
    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    payload = {
        "data": [
            {
                "type": "subtitle",
                "relationships": {
                    "feature": {"data": {"type": "feature", "id": "42"}},
                },
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "X"},
                },
            }
        ],
        "included": [
            {
                "type": "feature",
                "id": "42",
                "attributes": {"image": "https://img.example/poster.png"},
            }
        ],
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://img.example/poster.png"


def test_flatten_poster_protocol_relative_img_url():
    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "related_links": {"imgUrl": "//cdn.example/p/a.jpg"},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://cdn.example/p/a.jpg"
