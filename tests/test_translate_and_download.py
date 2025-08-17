import io
import re
import uuid


def make_srt():
    return ("""
1
00:00:01,000 --> 00:00:02,000
Hello world

2
00:00:03,000 --> 00:00:04,000
How are you?
""".strip() + "\n").encode("utf-8")


def post_translate(client, dual=False):
    data = {
        'sourceLanguage': 'en',
        'targetLanguage': 'zh-cn',
        'dualLanguage': 'true' if dual else 'false',
        'taskId': str(uuid.uuid4()),
    }
    srt_bytes = make_srt()
    resp = client.post(
        '/api/translate',
        data={
            **data,
            'srtFile': (io.BytesIO(srt_bytes), 'sample_en.srt'),
        },
        content_type='multipart/form-data',
        follow_redirects=True,
    )
    return resp


def test_translate_srt_non_dual(client, patch_translator):
    resp = post_translate(client, dual=False)
    assert resp.status_code == 200
    j = resp.get_json()
    assert j['success'] is True
    assert j['downloadUrl'].startswith('/api/download/')
    assert j['filename'].endswith('_zh-cn.srt')

    # Download file
    dl = client.get(j['downloadUrl'])
    assert dl.status_code == 200
    content = dl.data.decode('utf-8')
    # Our fake translator prefixes with ZH:
    assert 'ZH:' in content
    # Check header contains the server filename
    cd = dl.headers.get('Content-Disposition', '')
    assert j['filename'] in cd


def test_translate_srt_dual(client, patch_translator):
    resp = post_translate(client, dual=True)
    assert resp.status_code == 200
    j = resp.get_json()
    assert j['success'] is True
    assert j['downloadUrl'].startswith('/api/download/')
    assert j['filename'].endswith('_zh-cn_dual.srt')

    dl = client.get(j['downloadUrl'])
    assert dl.status_code == 200
    content = dl.data.decode('utf-8')
    # Should include both original and translated lines
    assert 'Hello world' in content
    assert 'ZH:Hello world' in content
    # Also check the second line presence
    assert 'How are you?' in content
    assert 'ZH:How are you?' in content
