import pytest

from srt_translator import create_app
from srt_translator.services.translation import translation_service


@pytest.fixture(scope="session")
def backend_module():
    class MockModule:
        def __init__(self):
            self.app = create_app()
            self.app.config["TESTING"] = True
            self.translation_service = translation_service

    return MockModule()


@pytest.fixture()
def app(backend_module):
    return backend_module.app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def patch_translator(monkeypatch, backend_module):
    async def fake_translate_texts(texts, source_lang, target_lang, translator):
        # Deterministic mapping to real Chinese for known phrases; fallback keeps old 'ZH:' prefix
        mapping = {
            "Hello world": "你好，世界",
            "How are you?": "你好吗？",
            "Hello": "你好",
        }
        output = []
        for t in texts:
            if t.strip():
                output.append(mapping.get(t, f"ZH:{t}"))
            else:
                output.append(t)
        return output

    monkeypatch.setattr(
        backend_module.translation_service,
        "translate_texts",
        fake_translate_texts,
        raising=True,
    )
    return True
