"""OpenSubtitles pager: next page loads second stub page."""

import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_search_pager_next_loads_second_page(page, base_url: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")

    page.get_by_label("Movie or show title").fill("e2e")
    page.get_by_role("button", name="Search subtitles").click()

    expect(page.locator("#osResultsTable")).to_be_visible(timeout=15_000)
    expect(page.locator("#osPageInfo")).to_contain_text("Page 1 of 2")
    expect(page.get_by_text("E2E Test Movie", exact=False)).to_be_visible()

    page.locator("#osPageNext").click()

    expect(page.locator("#osPageInfo")).to_contain_text("Page 2 of 2", timeout=15_000)
    expect(page.get_by_text("E2E Test Movie P2", exact=False)).to_be_visible()

    expect(page.locator("#osPagePrev")).to_be_enabled()
    expect(page.locator("#osPageNext")).to_be_disabled()
