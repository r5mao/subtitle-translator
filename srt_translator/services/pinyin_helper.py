"""Convert Chinese subtitle lines to spaced pinyin (tone marks)."""

from pypinyin import Style, lazy_pinyin


def line_to_pinyin(text: str) -> str:
    if not text or not text.strip():
        return ""
    return " ".join(lazy_pinyin(text, style=Style.TONE, neutral_tone_with_five=True))
