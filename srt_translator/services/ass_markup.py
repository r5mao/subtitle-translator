"""HTML inline styling to ASS override codes; plaintext extraction for translation."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_HTML_TAG_START = re.compile(r"<\s*/?\s*[a-zA-Z]")

_OPEN = {
    "i": r"{\i1}",
    "em": r"{\i1}",
    "italic": r"{\i1}",
    "b": r"{\b1}",
    "strong": r"{\b1}",
    "u": r"{\u1}",
    "s": r"{\s1}",
    "strike": r"{\s1}",
    "del": r"{\s1}",
}
_CLOSE = {
    "i": r"{\i0}",
    "em": r"{\i0}",
    "italic": r"{\i0}",
    "b": r"{\b0}",
    "strong": r"{\b0}",
    "u": r"{\u0}",
    "s": r"{\s0}",
    "strike": r"{\s0}",
    "del": r"{\s0}",
}


def ass_escape_plain_text(s: str) -> str:
    return (s or "").replace("\\", "\\\\")


def escape_ass_plain_runs(text: str) -> str:
    """Escape backslashes only outside ``{...}`` override blocks so existing ASS tags stay valid."""
    if not text:
        return ""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "{":
            j = text.find("}", i)
            if j == -1:
                out.append(ass_escape_plain_text(text[i:]))
                break
            out.append(text[i : j + 1])
            i = j + 1
        else:
            j = i
            while j < n and text[j] != "{":
                j += 1
            out.append(ass_escape_plain_text(text[i:j]))
            i = j
    return "".join(out)


class _HtmlStyleToAss(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t == "br":
            self._out.append(r"\N")
        elif t in _OPEN:
            self._out.append(_OPEN[t])

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in _CLOSE:
            self._out.append(_CLOSE[t])

    def handle_data(self, data: str) -> None:
        self._out.append(data)


def html_styling_tags_to_ass(text: str) -> str:
    """Map common HTML tags (e.g. ``<i>``) to ASS override codes. No-op if there are no HTML-like tags."""
    if not text or not _HTML_TAG_START.search(text):
        return text
    p = _HtmlStyleToAss()
    try:
        p.feed(text)
        p.close()
    except Exception:
        return text
    return "".join(p._out)


def plain_text_for_translation_ass(text: str) -> str:
    """Plain string for machine translation: HTML converted to ASS, then overrides and line breaks removed."""
    t = html_styling_tags_to_ass(text)
    t = re.sub(r"\{[^}]*\}", "", t)
    t = t.replace(r"\N", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t
