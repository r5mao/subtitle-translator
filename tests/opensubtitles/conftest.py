import pytest

from srt_translator.services.opensubtitles_client import reset_subtitle_language_names_cache


@pytest.fixture(autouse=True)
def _reset_os_language_cache():
    reset_subtitle_language_names_cache()
    yield
    reset_subtitle_language_names_cache()


@pytest.fixture
def os_env_configured(monkeypatch):
    monkeypatch.setenv("OPENSUBTITLES_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENSUBTITLES_USERNAME", "test-user")
    monkeypatch.setenv("OPENSUBTITLES_PASSWORD", "test-pass")
