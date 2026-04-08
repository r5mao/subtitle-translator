"""Batch machine translation over plain text lines."""

from __future__ import annotations

from googletrans import Translator

from srt_translator.services.translation import translation_service


async def translate_line_batches(
    lines: list[str],
    source_lang: str,
    translate_dest: str,
    update_progress,
) -> list[str]:
    out: list[str] = []
    async with Translator() as translator:
        batch_size = 100
        total = len(lines)
        for i in range(0, total, batch_size):
            batch = lines[i : i + batch_size]
            translated_batch = await translation_service.translate_texts(
                batch, source_lang, translate_dest, translator
            )
            out.extend(translated_batch)
            update_progress(min(i + batch_size, total), total)
    return out
