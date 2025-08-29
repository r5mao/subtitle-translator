import importlib.util
from pathlib import Path
import pytest

# Import the app factory from the new package structure
try:
    from srt_translator import create_app
    USE_NEW_STRUCTURE = True
except ImportError:
    # Fallback to legacy structure if new package not available
    USE_NEW_STRUCTURE = False
    BACKEND_PATH = Path(__file__).resolve().parents[1] / "venv" / "app.py"


@pytest.fixture(scope="session")
def backend_module():
    if USE_NEW_STRUCTURE:
        # Load the legacy module to get translation_service
        backend_path = Path(__file__).resolve().parents[1] / "venv" / "app.py"
        spec = importlib.util.spec_from_file_location("legacy_backend", str(backend_path))
        legacy_module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(legacy_module)
        
        # Create a mock module object for compatibility
        class MockModule:
            def __init__(self):
                self.app = create_app()
                self.app.config["TESTING"] = True
                # Get translation_service from the legacy module
                self.translation_service = getattr(legacy_module, 'translation_service', None)
        return MockModule()
    else:
        # Legacy path loading
        spec = importlib.util.spec_from_file_location("srt_backend_app", str(BACKEND_PATH))
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)  # type: ignore
        module.app.config["TESTING"] = True
        return module


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
