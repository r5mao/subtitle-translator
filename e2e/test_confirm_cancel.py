"""Translate confirm dialog: cancel leaves app idle (no completed translation)."""

import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_translate_confirm_cancel_skips_translation(page, base_url: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")

    page.get_by_label("Movie or show title").fill("e2e")
    page.get_by_role("button", name="Search subtitles").click()

    expect(page.locator("#osResultsTable")).to_be_visible(timeout=15_000)
    page.get_by_role("row", name=re.compile(r"Select subtitle:", re.I)).first.click()
    expect(page.get_by_role("row", name=re.compile(r"Selected:", re.I))).to_be_visible(
        timeout=15_000
    )

    page.locator("#sourceLanguage").select_option("en")
    page.locator("#targetLanguage").select_option("zh-cn")

    page.get_by_role("button", name=re.compile(r"Translate subtitles")).click()
    expect(page.locator("#translateConfirmDialog")).to_be_visible()

    page.locator("#translateConfirmCancel").click()
    expect(page.locator("#translateConfirmDialog")).not_to_be_visible()

    expect(page.locator("#downloadSection")).to_be_hidden()
    expect(page.get_by_text("Translation completed successfully")).not_to_be_visible()
