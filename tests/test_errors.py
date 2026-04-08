import io


def test_same_languages_rejected(client):
    resp = client.post(
        "/api/translate",
        data={"sourceLanguage": "en", "targetLanguage": "en", "taskId": "t1"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    j = resp.get_json()
    assert "error" in j


def test_invalid_extension_rejected(client):
    data = {"sourceLanguage": "en", "targetLanguage": "zh-cn", "taskId": "t2"}
    resp = client.post(
        "/api/translate",
        data={
            **data,
            "srtFile": (io.BytesIO(b"just text"), "not_subtitle.txt"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    j = resp.get_json()
    assert "error" in j


def test_invalid_download_id(client):
    resp = client.get("/api/download/not-a-uuid")
    assert resp.status_code == 400
    j = resp.get_json()
    assert "error" in j
