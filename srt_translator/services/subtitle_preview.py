"""First-cue subtitle preview JSON for UI (original + optional translation + pinyin)."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from googletrans import Translator

from srt_translator.services.pinyin_helper import line_to_pinyin
from srt_translator.services.subtitle_parser import SubtitleParser
from srt_translator.services.translation import (
    google_translate_dest,
    is_pinyin_target,
    translation_service,
)

logger = logging.getLogger(__name__)


def decode_subtitle_bytes(raw: bytes) -> str | None:
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def extract_first_cue_lines(fmt: str, parsed: Any) -> list[str]:
    if fmt == "srt" and parsed:
        first = parsed[0]
        return list(first.get("text_lines") or [])
    if fmt == "ass" and isinstance(parsed, dict) and parsed.get("dialogues"):
        t = (parsed["dialogues"][0].get("text") or "").strip()
        if t:
            return [re.sub(r"\{[^}]*\}", "", t).strip() or t]
        return []
    if fmt == "sub" and isinstance(parsed, dict) and parsed.get("subs"):
        t = (parsed["subs"][0].get("text") or "").strip()
        return [t] if t else []
    return []


def _preview_base(original_lines: list[str], fmt: str) -> dict[str, Any]:
    trimmed = original_lines[:4]
    return {
        "sampleLines": trimmed,
        "originalLines": trimmed,
        "translatedLines": None,
        "pinyinLines": None,
        "layout": "single",
        "format": fmt,
    }


def build_subtitle_preview_json(
    content: str,
    *,
    source_language: str,
    target_language: str,
    dual_language: bool,
    wants_translate: bool,
) -> dict[str, Any]:
    try:
        fmt, parsed = SubtitleParser.parse(content)
    except ValueError:
        return {
            "sampleLines": [],
            "originalLines": [],
            "translatedLines": None,
            "pinyinLines": None,
            "layout": "single",
            "format": "unknown",
        }

    orig = extract_first_cue_lines(fmt, parsed)
    base = _preview_base(orig, fmt)
    if not wants_translate or not orig:
        return base
    if source_language == target_language:
        return base
    if source_language not in translation_service.language_names:
        return base
    if target_language not in translation_service.language_names:
        return base

    trimmed = orig[:4]

    async def translate_lines() -> list[str]:
        google_dest = google_translate_dest(target_language)
        async with Translator() as translator:
            return await translation_service.translate_texts(
                trimmed, source_language, google_dest, translator
            )

    try:
        translated = asyncio.run(translate_lines())
    except Exception as e:
        logger.warning("Preview translation failed: %s", e)
        return base

    base["translatedLines"] = translated
    base["layout"] = "dual" if dual_language else "single"
    if is_pinyin_target(target_language):
        base["pinyinLines"] = [line_to_pinyin(t) for t in translated]
    return base
