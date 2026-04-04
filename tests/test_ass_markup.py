import pytest

from srt_translator.services.ass_markup import (
    escape_ass_plain_runs,
    html_styling_tags_to_ass,
    plain_text_for_translation_ass,
)


@pytest.mark.parametrize(
    "html,ass",
    [
        ("<i>x</i>", r"{\i1}x{\i0}"),
        ("<b>bold</b>", r"{\b1}bold{\b0}"),
        ("<strong>s</strong>", r"{\b1}s{\b0}"),
        ("<u>u</u>", r"{\u1}u{\u0}"),
        ("<s>z</s>", r"{\s1}z{\s0}"),
        ("<strike>z</strike>", r"{\s1}z{\s0}"),
        ("a<br>b", r"a\Nb"),
        ("a<br/>b", r"a\Nb"),
        ("a<BR />b", r"a\Nb"),
        ("<i>a</i> <b>b</b>", r"{\i1}a{\i0} {\b1}b{\b0}"),
    ],
)
def test_html_styling_tags_to_ass(html, ass):
    assert html_styling_tags_to_ass(html) == ass


def test_html_styling_no_tag_unchanged():
    assert html_styling_tags_to_ass(r"{\i1}Hi{\i0}") == r"{\i1}Hi{\i0}"
    assert html_styling_tags_to_ass("no angle brackets") == "no angle brackets"


def test_plain_text_for_translation_ass():
    assert plain_text_for_translation_ass("<i>Hello</i> world") == "Hello world"
    assert plain_text_for_translation_ass(r"{\i1}Hello{\i0}") == "Hello"
    assert plain_text_for_translation_ass("a<br>b") == "a b"


def test_escape_ass_plain_runs_preserves_overrides():
    inner = r"{\i1}Hello{\i0}"
    out = escape_ass_plain_runs(inner)
    assert out == inner


def test_escape_ass_plain_runs_escapes_backslash_outside():
    assert escape_ass_plain_runs(r"{\i1}C:\path{\i0}") == r"{\i1}C:\\path{\i0}"
