import io
import uuid


def make_srt():
    return (
        """
1
00:00:01,000 --> 00:00:02,000
Hello world

2
00:00:03,000 --> 00:00:04,000
How are you?
""".strip()
        + "\n"
    ).encode("utf-8")


def post_translate(client, dual=False, target_lang="zh-cn"):
    data = {
        "sourceLanguage": "en",
        "targetLanguage": target_lang,
        "dualLanguage": "true" if dual else "false",
        "taskId": str(uuid.uuid4()),
    }
    srt_bytes = make_srt()
    resp = client.post(
        "/api/translate",
        data={
            **data,
            "srtFile": (io.BytesIO(srt_bytes), "sample_en.srt"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    return resp


def test_translate_srt_non_dual(client, patch_translator):
    resp = post_translate(client, dual=False)
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] is True
    assert j["downloadUrl"].startswith("/api/download/")
    assert j["filename"].endswith("_zh-cn.srt")

    # Download file
    dl = client.get(j["downloadUrl"])
    assert dl.status_code == 200
    content = dl.data.decode("utf-8")
    # Our fake translator maps known phrases to Chinese for determinism
    assert "你好，世界" in content
    assert "你好吗？" in content
    # Check header contains the server filename
    cd = dl.headers.get("Content-Disposition", "")
    assert j["filename"] in cd


def test_translate_srt_pinyin_non_dual(client, patch_translator):
    resp = post_translate(client, dual=False, target_lang="zh-cn-pinyin")
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] is True
    assert j["filename"].endswith("_zh-cn-pinyin.ass")
    dl = client.get(j["downloadUrl"])
    assert dl.status_code == 200
    content = dl.data.decode("utf-8")
    assert "Dialogue:" in content
    assert "\\fs8" in content
    assert "\\fs12" in content
    assert "你好，世界" in content
    assert "nǐ" in content and "hǎo" in content


def test_translate_srt_pinyin_dual(client, patch_translator):
    resp = post_translate(client, dual=True, target_lang="zh-cn-pinyin")
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] is True
    assert j["filename"].endswith("_zh-cn-pinyin_dual.ass")
    dl = client.get(j["downloadUrl"])
    assert dl.status_code == 200
    content = dl.data.decode("utf-8")
    assert "Dialogue:" in content
    assert "\\fs8" in content
    assert "\\fs10" in content
    assert "\\fs12" in content
    assert "Hello world" in content
    assert "你好，世界" in content
    assert "nǐ" in content


def test_translate_srt_dual(client, patch_translator):
    resp = post_translate(client, dual=True)
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] is True
    assert j["downloadUrl"].startswith("/api/download/")
    assert j["filename"].endswith("_zh-cn_dual.srt")

    dl = client.get(j["downloadUrl"])
    assert dl.status_code == 200
    content = dl.data.decode("utf-8")
    # Should include both original and translated lines
    assert "Hello world" in content
    assert "你好，世界" in content
    # Also check the second line presence
    assert "How are you?" in content
    assert "你好吗？" in content


# ---- ASS/SUB helpers and tests ----


def make_ass():
    content = """[Script Info]
Title: Test
ScriptType: v4.00+
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello
Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,How are you?
"""
    return content.encode("utf-8")


def make_sub():
    content = """{0}{25}Hello
{26}{50}How are you?
"""
    return content.encode("utf-8")


def post_translate_file(
    client, filename: str, payload: bytes, dual: bool = False, target_lang="zh-cn"
):
    data = {
        "sourceLanguage": "en",
        "targetLanguage": target_lang,
        "dualLanguage": "true" if dual else "false",
        "taskId": str(uuid.uuid4()),
    }
    return client.post(
        "/api/translate",
        data={**data, "srtFile": (io.BytesIO(payload), filename)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_translate_ass_non_dual(client, patch_translator):
    resp = post_translate_file(client, "sample.ass", make_ass(), dual=False)
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] is True
    assert j["filename"].endswith("_zh-cn.ass")

    dl = client.get(j["downloadUrl"])
    assert dl.status_code == 200
    content = dl.data.decode("utf-8")
    assert "你好" in content
    assert "你好吗？" in content
    cd = dl.headers.get("Content-Disposition", "")
    assert j["filename"] in cd


def test_translate_ass_pinyin_dual(client, patch_translator):
    resp = post_translate_file(
        client, "sample.ass", make_ass(), dual=True, target_lang="zh-cn-pinyin"
    )
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["filename"].endswith("_zh-cn-pinyin_dual.ass")
    dl = client.get(j["downloadUrl"])
    content = dl.data.decode("utf-8")
    assert "{\\fs10}" in content
    assert "{\\fs12}" in content
    assert "{\\fs8}" in content
    assert "Hello" in content and "你好" in content
    assert "nǐ" in content


def test_translate_ass_dual(client, patch_translator):
    resp = post_translate_file(client, "sample.ass", make_ass(), dual=True)
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] is True
    assert j["filename"].endswith("_zh-cn_dual.ass")

    dl = client.get(j["downloadUrl"])
    assert dl.status_code == 200
    content = dl.data.decode("utf-8")
    assert "Hello" in content and "你好" in content
    assert "How are you?" in content and "你好吗？" in content


def test_translate_ass_dual_converts_html_styling_tags(client, patch_translator):
    ass_html = """[Script Info]
Title: Test
ScriptType: v4.00+
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,<i>Hello</i> <b>world</b>
"""
    resp = post_translate_file(
        client, "sample.ass", ass_html.encode("utf-8"), dual=True
    )
    assert resp.status_code == 200
    dl = client.get(resp.get_json()["downloadUrl"])
    content = dl.data.decode("utf-8")
    assert "{\\i1}" in content and "{\\i0}" in content
    assert "{\\b1}" in content and "{\\b0}" in content
    assert "<i>" not in content and "<b>" not in content
    assert "你好" in content


def test_translate_sub_non_dual(client, patch_translator):
    resp = post_translate_file(client, "sample.sub", make_sub(), dual=False)
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] is True
    assert j["filename"].endswith("_zh-cn.sub")

    dl = client.get(j["downloadUrl"])
    assert dl.status_code == 200
    content = dl.data.decode("utf-8")
    assert "你好" in content
    assert "你好吗？" in content


def test_translate_sub_dual(client, patch_translator):
    resp = post_translate_file(client, "sample.sub", make_sub(), dual=True)
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["success"] is True
    assert j["filename"].endswith("_zh-cn_dual.sub")

    dl = client.get(j["downloadUrl"])
    assert dl.status_code == 200
    content = dl.data.decode("utf-8")
    # SUB dual uses | between original and translation
    assert "Hello|你好" in content
    assert "How are you?|你好吗？" in content
