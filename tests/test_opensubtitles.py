import os
import tempfile
import uuid

import pytest

from tests.test_translate_and_download import make_srt


class _FakeOpenSubtitlesClient:
    """Stub for OpenSubtitlesClient in route tests."""

    def __init__(self):
        pass

    def configured(self):
        return True

    def search(self, query, languages="", page=1):
        assert query.strip()
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
                    },
                }
            ],
            "total_pages": 1,
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
    assert row["title"] == "Test Movie"


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
