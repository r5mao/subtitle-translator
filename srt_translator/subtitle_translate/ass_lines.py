"""ASS-style line snippets and collapse helpers for translated subtitle output."""

from __future__ import annotations

import re

from srt_translator.services.ass_markup import (
    ass_escape_plain_text,
    escape_ass_plain_runs,
)


def ass_english_line(text: str) -> str:
    return f"{{\\fs10}}{escape_ass_plain_runs(text)}{{\\r}}"


def ass_chinese_line(text: str) -> str:
    return f"{{\\fs12}}{escape_ass_plain_runs(text)}{{\\r}}"


def ass_pinyin_line(pinyin_plain: str) -> str:
    return f"{{\\fs8}}{ass_escape_plain_text(pinyin_plain)}{{\\r}}"


def join_srt_text_lines(lines: list) -> str:
    return " ".join(x.strip() for x in (lines or []) if x.strip())


def collapse_ass_dialogue(text: str) -> str:
    if not text:
        return ""
    return " ".join(p.strip() for p in text.split(r"\N") if p.strip())


def collapse_sub_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(p.strip() for p in re.split(r"[\r\n]+", text) if p.strip())


def format_translation_duration(total_ms: int) -> str:
    duration_minutes = total_ms // 60000
    duration_seconds = (total_ms % 60000) // 1000
    duration_ms = total_ms % 1000
    if duration_minutes:
        return f"{duration_minutes} mins {duration_seconds} seconds {duration_ms} ms"
    if duration_seconds:
        return f"{duration_seconds} seconds {duration_ms} ms"
    return f"{duration_ms} ms"
