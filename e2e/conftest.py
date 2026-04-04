"""
E2E fixtures: live Flask, fake OpenSubtitles (zero real API calls), fake translator.

Assertion style (refactor-friendly): prefer getByRole / getByLabel and downloaded
file text. Add data-testid only if roles cannot disambiguate dynamic rows.

OpenSubtitles: default E2E uses a stub client so CI and local runs do not hit
rate limits. Optional @pytest.mark.live_opensubtitles is reserved for future
manual/nightly tests with narrow queries — not enabled here.
"""

from __future__ import annotations

import threading
import time
import unittest.mock as mock
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from srt_translator import create_app
from srt_translator.api import opensubtitles_routes as os_routes
from srt_translator.services import opensubtitles_client as osc
from srt_translator.services.translation import translation_service

pytest_plugins = ["pytest_playwright"]

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _minimal_srt_bytes() -> bytes:
    return (_FIXTURES_DIR / "sample_en.srt").read_bytes()


def _fake_search_api_json() -> dict:
    """JSON shape consumed by flatten_subtitle_results / suggestions."""
    return {
        "data": [
            {
                "type": "subtitle",
                "attributes": {
                    "language": "en",
                    "release": "E2E",
                    "files": [
                        {"file_id": "999001", "file_name": "e2e_fixture.srt"},
                    ],
                    "feature_details": {
                        "title": "E2E Test Movie",
                        "year": 2001,
                    },
                },
            }
        ],
        "meta": {"total_pages": 1, "total_count": 1},
    }


async def _fake_translate_texts(texts, source_lang, target_lang, translator):
    mapping = {
        "Hello world": "你好，世界",
        "How are you?": "你好吗？",
        "Hello": "你好",
    }
    out = []
    for t in texts:
        if t.strip():
            out.append(mapping.get(t, f"ZH:{t}"))
        else:
            out.append(t)
    return out


class _FakeOpenSubtitlesClient:
    """Stub: no network; search returns one English row; download returns fixture SRT."""

    def configured(self) -> bool:
        return True

    def login(self, force: bool = False) -> None:
        return None

    def fetch_language_names(self) -> dict[str, str]:
        return {
            "en": "English",
            "zh-cn": "Chinese (Simplified)",
            "zh-cn-pinyin": "Chinese (Simplified) + Pinyin",
        }

    def search(
        self,
        query: str,
        *,
        languages: str = "",
        page: int = 1,
        per_page: int = 10,
        year=None,
        imdb_id=None,
    ) -> dict:
        return _fake_search_api_json()

    def download_file(self, file_id: str) -> tuple[bytes, str]:
        return (_minimal_srt_bytes(), "e2e_fixture.srt")


@pytest.fixture(scope="session")
def live_server_url():
    """Threaded Flask on an ephemeral port; patches active for the whole session."""
    osc._subtitle_language_names_cache = None

    p_os = mock.patch.object(os_routes, "OpenSubtitlesClient", _FakeOpenSubtitlesClient)
    p_tr = mock.patch.object(
        translation_service,
        "translate_texts",
        side_effect=_fake_translate_texts,
    )
    p_os.start()
    p_tr.start()

    app = create_app()
    app.config["TESTING"] = True

    server_holder: list = []
    port_holder: list = [None]

    def serve():
        srv = make_server("127.0.0.1", 0, app, threaded=True)
        port_holder[0] = srv.server_port
        server_holder.append(srv)
        srv.serve_forever()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    for _ in range(100):
        if port_holder[0] is not None:
            break
        time.sleep(0.05)
    if port_holder[0] is None:
        p_os.stop()
        p_tr.stop()
        raise RuntimeError("Live server failed to bind")

    base = f"http://127.0.0.1:{port_holder[0]}"
    try:
        yield base
    finally:
        if server_holder:
            server_holder[0].shutdown()
        p_os.stop()
        p_tr.stop()
        osc._subtitle_language_names_cache = None


@pytest.fixture(scope="session")
def base_url(live_server_url: str) -> str:
    return live_server_url


@pytest.fixture
def sample_srt_path() -> Path:
    return _FIXTURES_DIR / "sample_en.srt"
