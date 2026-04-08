def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "SRT Translation API"


def test_languages(client):
    resp = client.get("/api/languages")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "languages" in data
    langs = data["languages"]
    # Sanity checks
    assert "en" in langs
    assert "zh-cn" in langs
    assert langs["zh-cn"].lower().startswith("chinese")
    assert "zh-cn-pinyin" in langs
    assert "pinyin" in langs["zh-cn-pinyin"].lower()
