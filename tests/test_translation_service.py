"""Unit tests for TranslationService.translate_texts (real async body, fake translator)."""

import asyncio
import types

from srt_translator.services.translation import TranslationService


def _run_translate_texts(service, texts, source_lang, target_lang, fake_translator):
    return asyncio.run(
        service.translate_texts(texts, source_lang, target_lang, fake_translator)
    )


class FakeTranslatorList:
    """Returns a list of objects with .text (batch path)."""

    def __init__(self):
        self.calls = []

    async def translate(self, to_translate, dest=None, src=None):
        self.calls.append(
            {"to_translate": list(to_translate), "dest": dest, "src": src}
        )
        return [types.SimpleNamespace(text=f"TR:{t}") for t in to_translate]


class FakeTranslatorSingle:
    """Returns one object with .text (single-result branch)."""

    def __init__(self):
        self.calls = []

    async def translate(self, to_translate, dest=None, src=None):
        self.calls.append(
            {"to_translate": list(to_translate), "dest": dest, "src": src}
        )
        assert len(to_translate) == 1
        return types.SimpleNamespace(text=f"TR:{to_translate[0]}")


class FakeTranslatorNoCall:
    def __init__(self):
        self.calls = []

    async def translate(self, to_translate, dest=None, src=None):
        self.calls.append(to_translate)
        raise AssertionError(
            "translate should not be called when there is nothing to translate"
        )


def test_translate_texts_list_result():
    service = TranslationService()
    fake = FakeTranslatorList()
    texts = ["Hello", "World"]
    out = _run_translate_texts(service, texts, "en", "es", fake)

    assert out == ["TR:Hello", "TR:World"]
    assert len(fake.calls) == 1
    assert fake.calls[0]["to_translate"] == ["Hello", "World"]
    assert fake.calls[0]["dest"] == "es"
    assert fake.calls[0]["src"] == "en"


def test_translate_texts_single_result():
    service = TranslationService()
    fake = FakeTranslatorSingle()
    texts = ["Only one"]
    out = _run_translate_texts(service, texts, "en", "fr", fake)

    assert out == ["TR:Only one"]
    assert fake.calls[0]["to_translate"] == ["Only one"]
    assert fake.calls[0]["dest"] == "fr"


def test_translate_texts_all_whitespace_returns_original_without_translate():
    service = TranslationService()
    fake = FakeTranslatorNoCall()
    texts = ["", "  \t", "\n"]
    out = _run_translate_texts(service, texts, "en", "de", fake)

    assert out is texts
    assert fake.calls == []


def test_translate_texts_mixed_empty_preserves_originals_and_batches_only_nonempty():
    service = TranslationService()
    fake = FakeTranslatorList()
    texts = ["", "  ", "Hello", "\t"]
    out = _run_translate_texts(service, texts, "en", "ja", fake)

    assert out == ["", "  ", "TR:Hello", "\t"]
    assert len(fake.calls) == 1
    assert fake.calls[0]["to_translate"] == ["Hello"]
