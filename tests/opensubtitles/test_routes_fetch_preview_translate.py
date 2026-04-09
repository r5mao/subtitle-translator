import contextlib
import gc
import os
import tempfile
import uuid

from tests.opensubtitles.support import (
    FakeMultiFilePerSubtitle,
    FakeOpenSubtitlesClient,
    FakeSuggestionsDupFeature,
)
from tests.test_translate_and_download import make_srt


def test_opensubtitles_suggestions_ok(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeSuggestionsDupFeature,
    )
    resp = client.post("/api/opensubtitles/suggestions", json={"query": "ab"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["suggestions"]) == 2
    assert FakeSuggestionsDupFeature.last_search["languages"] == ""
    assert FakeSuggestionsDupFeature.last_search["per_page"] == 50


def test_opensubtitles_suggestions_rejects_short_query(
    client, os_env_configured, monkeypatch
):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
    )
    resp = client.post("/api/opensubtitles/suggestions", json={"query": "a"})
    assert resp.status_code == 400


def test_opensubtitles_suggestions_503_without_credentials(client, monkeypatch):
    monkeypatch.delenv("OPENSUBTITLES_API_KEY", raising=False)
    monkeypatch.delenv("OPENSUBTITLES_USERNAME", raising=False)
    monkeypatch.delenv("OPENSUBTITLES_PASSWORD", raising=False)
    resp = client.post("/api/opensubtitles/suggestions", json={"query": "ab"})
    assert resp.status_code == 503


def test_opensubtitles_search_caps_flattened_rows_to_per_page(
    client, os_env_configured, monkeypatch
):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeMultiFilePerSubtitle,
    )
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.get_language_name_lookup",
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
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
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


def test_opensubtitles_fetched_download_streams_file(
    client, os_env_configured, monkeypatch
):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
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
    with contextlib.suppress(OSError):
        os.remove(os.path.join(temp_dir, matches[0]))


def test_opensubtitles_fetched_download_404_unknown_id(client):
    resp = client.get(f"/api/opensubtitles/fetched/{uuid.uuid4()}/download")
    assert resp.status_code == 404


def test_opensubtitles_fetched_download_400_bad_id(client):
    resp = client.get("/api/opensubtitles/fetched/not-a-uuid/download")
    assert resp.status_code == 400


def test_opensubtitles_fetched_preview_json(client, os_env_configured, monkeypatch):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
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


def test_opensubtitles_fetched_preview_post_translated(
    client, os_env_configured, monkeypatch, patch_translator
):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
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


def test_opensubtitles_fetched_preview_post_pinyin_target(
    client, os_env_configured, monkeypatch, patch_translator
):
    monkeypatch.setattr(
        "srt_translator.api.opensubtitles_search_handlers.OpenSubtitlesClient",
        FakeOpenSubtitlesClient,
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
        assert os.path.exists(path), (
            "fetched temp file should remain after translate for re-translate / download original"
        )
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
