"""OpenSubtitles path: search → select → download original (no translation)."""

import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_search_download_original_subtitle(page, base_url: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")

    page.locator("#translateToOtherLang").set_checked(False)
    expect(page.get_by_role("button", name=re.compile(r"Download subtitle"))).to_be_visible()

    page.get_by_label("Movie or show title").fill("e2e")
    page.get_by_role("button", name="Search subtitles").click()

    expect(page.locator("#osResultsTable")).to_be_visible(timeout=15_000)
    page.get_by_role("row", name=re.compile(r"Select subtitle:", re.I)).first.click()
    expect(page.get_by_role("row", name=re.compile(r"Selected:", re.I))).to_be_visible(
        timeout=15_000
    )

    page.get_by_role("button", name=re.compile(r"Download subtitle")).click()

    expect(page.get_by_text("Subtitle file ready.")).to_be_visible(timeout=60_000)
    download_link = page.get_by_role(
        "link", name=re.compile(r"Download original subtitle")
    )

    with page.expect_download(timeout=60_000) as dl:
        download_link.click()
    path = dl.value.path()
    assert path is not None
    text = path.read_text(encoding="utf-8")

    assert "Hello world" in text
    assert "How are you?" in text
    assert "你好" not in text
