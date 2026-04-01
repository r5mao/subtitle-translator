import gc
import os
import tempfile
import urllib.parse
import uuid

import pytest

from srt_translator.services.opensubtitles_client import (
    clean_work_search_query,
    distinct_work_suggestions_from_subtitles,
    normalize_opensubtitles_imdb_id,
    reset_subtitle_language_names_cache,
)
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

    def search(self, query, languages="", page=1, per_page=10, *, year=None, imdb_id=None, **kwargs):
        assert query.strip()
        type(self).last_search = {
            "query": query,
            "languages": languages,
            "page": page,
            "per_page": per_page,
            "year": year,
            "imdb_id": imdb_id,
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
    assert data["perPage"] == 10
    assert data["totalPages"] == 3
    assert data["totalCount"] == 75
    assert _FakeOpenSubtitlesClient.last_search["per_page"] == 10


class _FakeOpenSubtitlesManyPages(_FakeOpenSubtitlesClient):
    """Upstream reports more pages than we expose to the client."""

    def search(self, query, languages="", page=1, per_page=10, *, year=None, imdb_id=None, **kwargs):
        out = super().search(
            query,
            languages=languages,
            page=page,
            per_page=per_page,
            year=year,
            imdb_id=imdb_id,
            **kwargs,
        )
        out = dict(out)
        out["total_pages"] = 50
        return out


def test_opensubtitles_search_caps_total_pages(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeOpenSubtitlesManyPages,
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
    assert resp.get_json()["totalPages"] == 10


def test_opensubtitles_search_rejects_page_above_cap(client, os_env_configured, monkeypatch):
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
        json={"query": "Test Movie", "language": "en", "page": 11},
    )
    assert resp.status_code == 400


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


def test_normalize_opensubtitles_imdb_id():
    assert normalize_opensubtitles_imdb_id("tt0133093") == "0133093"
    assert normalize_opensubtitles_imdb_id(1330933) == "1330933"
    assert normalize_opensubtitles_imdb_id("bad") is None


def test_opensubtitles_search_passes_year_and_imdb_to_client(client, os_env_configured, monkeypatch):
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
        json={
            "query": "The Matrix",
            "language": "en",
            "page": 1,
            "year": 1999,
            "imdbId": "tt0133093",
        },
    )
    assert resp.status_code == 200
    assert _FakeOpenSubtitlesClient.last_search["year"] == 1999
    assert _FakeOpenSubtitlesClient.last_search["imdb_id"] == "0133093"


def test_opensubtitles_search_ignores_out_of_range_year(client, os_env_configured, monkeypatch):
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
        json={"query": "Test Movie", "language": "en", "year": 1700},
    )
    assert resp.status_code == 200
    assert _FakeOpenSubtitlesClient.last_search.get("year") is None


class _FakeSuggestionsDupFeature(_FakeOpenSubtitlesClient):
    """Two subtitle rows share one feature id; third row is another feature."""

    def search(self, query, languages="", page=1, per_page=10, *, year=None, imdb_id=None, **kwargs):
        assert query.strip()
        type(self).last_search = {
            "query": query,
            "languages": languages,
            "page": page,
            "per_page": per_page,
            "year": year,
            "imdb_id": imdb_id,
        }
        return {
            "data": [
                {
                    "type": "subtitle",
                    "relationships": {"feature": {"data": {"type": "feature", "id": "42"}}},
                    "attributes": {
                        "language": "en",
                        "release": "R1",
                        "files": [{"file_id": 1, "file_name": "a.srt"}],
                        "feature_details": {"movie_name": "Same Movie", "year": 2019},
                        "related_links": {"img_url": "https://example.com/p1.jpg"},
                    },
                },
                {
                    "type": "subtitle",
                    "relationships": {"feature": {"data": {"type": "feature", "id": "42"}}},
                    "attributes": {
                        "language": "es",
                        "release": "R2",
                        "files": [{"file_id": 2, "file_name": "b.srt"}],
                        "feature_details": {"movie_name": "Same Movie", "year": 2019},
                    },
                },
                {
                    "type": "subtitle",
                    "relationships": {"feature": {"data": {"type": "feature", "id": "99"}}},
                    "attributes": {
                        "language": "en",
                        "release": "R3",
                        "files": [{"file_id": 3, "file_name": "c.srt"}],
                        "feature_details": {"movie_name": "Other Movie", "year": 2021},
                    },
                },
            ],
        }


def test_clean_work_search_query_strips_opensubtitles_year_patterns():
    assert clean_work_search_query("1999 - The Matrix", 1999) == "The Matrix"
    assert clean_work_search_query("The Matrix (1999)", 1999) == "The Matrix"
    assert clean_work_search_query("The Matrix", 1999) == "The Matrix"
    assert clean_work_search_query("  2010  -  Some Film ", 2010) == "Some Film"


def test_distinct_work_suggestions_dedupes_same_feature():
    c = _FakeSuggestionsDupFeature()
    raw = c.search("x", languages="", page=1, per_page=50)
    sugs = distinct_work_suggestions_from_subtitles(raw, limit=10)
    assert len(sugs) == 2
    assert sugs[0]["title"] == "Same Movie"
    assert sugs[0]["searchQuery"] == "Same Movie"
    assert sugs[0]["year"] == 2019
    assert sugs[0]["posterUrl"] == "https://example.com/p1.jpg"
    assert sugs[0]["featureId"] == "42"
    assert sugs[1]["title"] == "Other Movie"
    assert sugs[1]["searchQuery"] == "Other Movie"
    assert sugs[1]["year"] == 2021
    assert sugs[1]["featureId"] == "99"


def test_opensubtitles_suggestions_ok(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeSuggestionsDupFeature,
    )
    resp = client.post("/api/opensubtitles/suggestions", json={"query": "ab"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["suggestions"]) == 2
    assert _FakeSuggestionsDupFeature.last_search["languages"] == ""
    assert _FakeSuggestionsDupFeature.last_search["per_page"] == 50


def test_opensubtitles_suggestions_rejects_short_query(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeOpenSubtitlesClient,
    )
    resp = client.post("/api/opensubtitles/suggestions", json={"query": "a"})
    assert resp.status_code == 400


def test_opensubtitles_suggestions_503_without_credentials(client, monkeypatch):
    monkeypatch.delenv("OPENSUBTITLES_API_KEY", raising=False)
    monkeypatch.delenv("OPENSUBTITLES_USERNAME", raising=False)
    monkeypatch.delenv("OPENSUBTITLES_PASSWORD", raising=False)
    resp = client.post("/api/opensubtitles/suggestions", json={"query": "ab"})
    assert resp.status_code == 503


class _FakeMultiFilePerSubtitle(_FakeOpenSubtitlesClient):
    """Each API subtitle has multiple files; flatten yields more rows than per_page."""

    def search(self, query, languages="", page=1, per_page=10, *, year=None, imdb_id=None, **kwargs):
        assert query.strip()
        type(self).last_search = {
            "query": query,
            "languages": languages,
            "page": page,
            "per_page": per_page,
            "year": year,
            "imdb_id": imdb_id,
        }
        data_items = []
        for i in range(5):
            data_items.append(
                {
                    "type": "subtitle",
                    "attributes": {
                        "language": "en",
                        "release": f"Release.{i}",
                        "download_count": 1,
                        "fps": 23.976,
                        "files": [
                            {"file_id": 880000 + i * 10 + j, "file_name": f"sub_{i}_{j}.srt"}
                            for j in range(3)
                        ],
                        "feature_details": {
                            "movie_name": "Multi CD",
                            "year": 2020,
                        },
                        "related_links": {
                            "img_url": "https://example.com/poster.jpg",
                        },
                    },
                }
            )
        return {
            "data": data_items,
            "total_pages": 1,
            "total_count": 5,
        }


def test_opensubtitles_search_caps_flattened_rows_to_per_page(
    client, os_env_configured, monkeypatch
):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeMultiFilePerSubtitle,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.get_language_name_lookup",
        lambda _c: {"en": "English"},
    )
    resp = client.post(
        "/api/opensubtitles/search",
        json={"query": "Multi", "language": "en", "page": 1, "perPage": 10},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["perPage"] == 10
    assert len(data["results"]) == 10


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


def test_opensubtitles_fetched_download_streams_file(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeOpenSubtitlesClient,
    )
    resp = client.post("/api/opensubtitles/fetch", json={"file_id": "999001"})
    assert resp.status_code == 200
    fid = resp.get_json()["fetchedId"]
    dl = client.get(f"/api/opensubtitles/fetched/{fid}/download")
    assert dl.status_code == 200
    assert b"1\n00:00:01,000" in dl.data or make_srt().split(b"\n")[0] in dl.data
    assert "attachment" in (dl.headers.get("Content-Disposition") or "").lower()
    temp_dir = tempfile.gettempdir()
    matches = [f for f in os.listdir(temp_dir) if f.startswith(f"{fid}_")]
    assert len(matches) == 1
    del dl
    gc.collect()
    try:
        os.remove(os.path.join(temp_dir, matches[0]))
    except OSError:
        pass


def test_opensubtitles_fetched_download_404_unknown_id(client):
    resp = client.get(f"/api/opensubtitles/fetched/{uuid.uuid4()}/download")
    assert resp.status_code == 404


def test_opensubtitles_fetched_download_400_bad_id(client):
    resp = client.get("/api/opensubtitles/fetched/not-a-uuid/download")
    assert resp.status_code == 400


def test_opensubtitles_fetched_preview_json(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeOpenSubtitlesClient,
    )
    resp = client.post("/api/opensubtitles/fetch", json={"file_id": "999001"})
    fid = resp.get_json()["fetchedId"]
    prev = client.get(f"/api/opensubtitles/fetched/{fid}/preview")
    assert prev.status_code == 200
    data = prev.get_json()
    assert "sampleLines" in data
    assert isinstance(data["sampleLines"], list)
    assert data["sampleLines"] and "Hello world" in data["sampleLines"][0]
    assert data.get("originalLines") == data["sampleLines"]
    assert data.get("translatedLines") is None
    temp_dir = tempfile.gettempdir()
    for f in os.listdir(temp_dir):
        if f.startswith(f"{fid}_"):
            os.remove(os.path.join(temp_dir, f))
            break


def test_opensubtitles_fetched_preview_post_translated(client, os_env_configured, monkeypatch, patch_translator):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeOpenSubtitlesClient,
    )
    resp = client.post("/api/opensubtitles/fetch", json={"file_id": "999001"})
    fid = resp.get_json()["fetchedId"]
    try:
        prev = client.post(
            f"/api/opensubtitles/fetched/{fid}/preview",
            json={
                "sourceLanguage": "en",
                "targetLanguage": "zh-cn",
                "dualLanguage": True,
                "wantsTranslate": True,
            },
        )
        assert prev.status_code == 200
        data = prev.get_json()
        assert data["translatedLines"]
        assert "你好" in data["translatedLines"][0]
        assert data.get("pinyinLines") is None
    finally:
        temp_dir = tempfile.gettempdir()
        for f in os.listdir(temp_dir):
            if f.startswith(f"{fid}_"):
                os.remove(os.path.join(temp_dir, f))
                break


def test_opensubtitles_fetched_preview_post_pinyin_target(client, os_env_configured, monkeypatch, patch_translator):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_routes.OpenSubtitlesClient",
        _FakeOpenSubtitlesClient,
    )
    resp = client.post("/api/opensubtitles/fetch", json={"file_id": "999001"})
    fid = resp.get_json()["fetchedId"]
    try:
        prev = client.post(
            f"/api/opensubtitles/fetched/{fid}/preview",
            json={
                "sourceLanguage": "en",
                "targetLanguage": "zh-cn-pinyin",
                "dualLanguage": False,
                "wantsTranslate": True,
            },
        )
        assert prev.status_code == 200
        data = prev.get_json()
        assert data["translatedLines"]
        assert data.get("pinyinLines")
        assert len(data["pinyinLines"]) == len(data["translatedLines"])
    finally:
        temp_dir = tempfile.gettempdir()
        for f in os.listdir(temp_dir):
            if f.startswith(f"{fid}_"):
                os.remove(os.path.join(temp_dir, f))
                break


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


def test_flatten_poster_relative_path_on_opensubtitles_com():
    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "related_links": {"img_url": "/pictures/posters/abc.jpg"},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://www.opensubtitles.com/pictures/posters/abc.jpg"


def test_flatten_poster_deep_nested_string():
    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {
                        "movie_name": "X",
                        "nested": {"note": "see https://s9.osdb.link/features/1/2/3/z.jpg"},
                    },
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://s9.osdb.link/features/1/2/3/z.jpg"


def test_flatten_poster_tmdb_falls_back_to_tv_when_movie_has_no_posters(monkeypatch):
    import json

    import urllib.request

    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    monkeypatch.setenv("TMDB_API_KEY", "k")
    calls: list[str] = []

    def fake_urlopen(req, *a, **k):
        u = getattr(req, "full_url", None) or req.get_full_url()
        calls.append(u)

        class R:
            def __init__(self, body: bytes):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        if "/movie/" in u:
            return R(json.dumps({"posters": []}).encode("utf-8"))
        if "/tv/" in u:
            return R(json.dumps({"posters": [{"file_path": "/from-tv.jpg"}]}).encode("utf-8"))
        raise AssertionError(f"unexpected urlopen url: {u}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "Some Show", "tmdb_id": 1399},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://image.tmdb.org/t/p/w185/from-tv.jpg"
    assert len(calls) == 2
    assert "/movie/1399/" in calls[0]
    assert "/tv/1399/" in calls[1]


def test_flatten_poster_tmdb_fallback(monkeypatch):
    import json

    import urllib.request

    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    monkeypatch.setenv("TMDB_API_KEY", "test-tmdb-key")

    class FakeResp:
        def read(self):
            return json.dumps({"posters": [{"file_path": "/abc.jpg"}]}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: FakeResp())

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "X", "tmdb_id": 550},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://image.tmdb.org/t/p/w185/abc.jpg"


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
    import urllib.request

    from srt_translator.api import opensubtitles_routes as routes_mod

    class FakeResp:
        headers = {"Content-Type": "image/jpeg"}

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
    monkeypatch.setattr(routes_mod, "_POSTER_TIMEOUT_SEC", 5)

    u = urllib.parse.quote("https://s9.osdb.link/features/1/2/3/x.jpg", safe="")
    resp = client.get(f"/api/opensubtitles/poster-image?url={u}")
    assert resp.status_code == 200
    assert resp.data.startswith(b"\xff\xd8\xff")
    assert "image" in (resp.headers.get("Content-Type") or "").lower()


def test_poster_image_allows_amazon_imdb_style_host(client, monkeypatch):
    import urllib.request

    from srt_translator.api import opensubtitles_routes as routes_mod

    class FakeResp:
        headers = {"Content-Type": "image/jpeg"}

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
    monkeypatch.setattr(routes_mod, "_POSTER_TIMEOUT_SEC", 5)

    u = urllib.parse.quote("https://m.media-amazon.com/images/M/poster.jpg", safe="")
    resp = client.get(f"/api/opensubtitles/poster-image?url={u}")
    assert resp.status_code == 200


def test_maybe_absolutize_opensubtitles_poster_paths():
    """Site-relative poster paths must become absolute https URLs for the UI proxy."""
    from srt_translator.services.opensubtitles_client import _maybe_absolutize_opensubtitles_image_url

    assert (
        _maybe_absolutize_opensubtitles_image_url("/pictures/posters/x.jpg")
        == "https://www.opensubtitles.com/pictures/posters/x.jpg"
    )
    assert _maybe_absolutize_opensubtitles_image_url("//img.example/a.png") == "https://img.example/a.png"
    assert _maybe_absolutize_opensubtitles_image_url("https://cdn.example/z.webp") == "https://cdn.example/z.webp"
    assert _maybe_absolutize_opensubtitles_image_url("/pictures/../evil.jpg") is None


def test_tmdb_poster_api_and_cdn_url_construction(monkeypatch):
    """TMDb images request and resulting image.tmdb.org poster URL must follow a fixed shape."""
    import json

    import urllib.request

    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    monkeypatch.setenv("TMDB_API_KEY", "k")
    seen: list[str] = []

    class FakeResp:
        def read(self):
            return json.dumps(
                {
                    "posters": [{"file_path": "/movie/poster1.jpg"}],
                    "backdrops": [{"file_path": "/movie/backdrop1.jpg"}],
                }
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def capture_urlopen(req, *a, **k):
        seen.append(getattr(req, "full_url", None) or req.get_full_url())
        return FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", capture_urlopen)

    payload = {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "X", "tmdb_id": 999},
                },
            }
        ]
    }
    rows = flatten_subtitle_results(payload)
    assert len(seen) == 1
    assert seen[0].startswith("https://api.themoviedb.org/3/movie/999/images?")
    assert "api_key=k" in seen[0]
    assert rows[0]["posterUrl"] == "https://image.tmdb.org/t/p/w185/movie/poster1.jpg"
    assert rows[0]["backdropUrl"] == "https://image.tmdb.org/t/p/w780/movie/backdrop1.jpg"


def test_flatten_poster_from_included_movie_resource():
    """Shows may sideload poster on type=movie via relationships.movie."""
    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    payload = {
        "data": [
            {
                "type": "subtitle",
                "relationships": {"movie": {"data": {"type": "movie", "id": "77"}}},
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "ep.srt"}],
                    "feature_details": {"movie_name": "Some Show", "season_number": 1, "episode_number": 2},
                },
            }
        ],
        "included": [
            {
                "type": "movie",
                "id": "77",
                "attributes": {
                    "poster_url": "https://s9.osdb.link/features/show/77.jpg",
                    "feature_details": {},
                },
            }
        ],
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://s9.osdb.link/features/show/77.jpg"


def test_flatten_poster_from_included_parent_resource():
    """Episode rows may link poster via relationships.parent."""
    from srt_translator.services.opensubtitles_client import flatten_subtitle_results

    payload = {
        "data": [
            {
                "type": "subtitle",
                "relationships": {"parent": {"data": {"type": "feature", "id": "p1"}}},
                "attributes": {
                    "language": "en",
                    "files": [{"file_id": 1, "file_name": "a.srt"}],
                    "feature_details": {"movie_name": "Ep Title"},
                },
            }
        ],
        "included": [
            {
                "type": "feature",
                "id": "p1",
                "attributes": {"image": "https://img.example/parent-poster.png"},
            }
        ],
    }
    rows = flatten_subtitle_results(payload)
    assert rows[0]["posterUrl"] == "https://img.example/parent-poster.png"


def test_poster_image_proxy_query_url_construction_roundtrip():
    """Mirrors static/js/main.js posterProxySrc: path must decode back to the remote poster URL."""
    api_base = "http://127.0.0.1:5555"
    remote = "https://s9.osdb.link/features/1/2/3/poster.jpg?token=x&raw=1"
    q = urllib.parse.quote(remote, safe="")
    proxy = f"{api_base.rstrip('/')}/api/opensubtitles/poster-image?url={q}"
    parsed = urllib.parse.urlparse(proxy)
    qs = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
    assert urllib.parse.unquote(qs["url"][0]) == remote


def test_poster_image_allows_cloudfront(client, monkeypatch):
    import urllib.request

    from srt_translator.api import opensubtitles_routes as routes_mod

    class FakeResp:
        headers = {"Content-Type": "image/jpeg"}

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
    monkeypatch.setattr(routes_mod, "_POSTER_TIMEOUT_SEC", 5)

    u = urllib.parse.quote("https://d111111abcdef8.cloudfront.net/out/poster.jpg", safe="")
    resp = client.get(f"/api/opensubtitles/poster-image?url={u}")
    assert resp.status_code == 200
    assert resp.data.startswith(b"\xff\xd8\xff")


def test_subtitles_search_retries_without_include_on_400(monkeypatch):
    from srt_translator.services.opensubtitles_client import OpenSubtitlesClient, OpenSubtitlesError

    calls: list[tuple] = []

    def fake_request(self, method, path, *, query=None, json_body=None, retry_login=True):
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
