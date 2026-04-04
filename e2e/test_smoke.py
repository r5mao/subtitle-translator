"""Fast sanity checks: no full translate journey."""

import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def test_home_loads_and_toggle_upload_source(page, base_url: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name=re.compile(r"Subtitle Translator"))).to_be_visible()
    expect(page.locator("#translationForm")).to_be_visible()
    expect(page.locator("#languageSection")).to_be_visible()

    page.locator("#sourceUpload").check()
    expect(page.locator("#uploadPanel")).to_be_visible()
    expect(page.locator("#searchPanel")).to_be_hidden()

    page.locator("#sourceSearch").check()
    expect(page.locator("#searchPanel")).to_be_visible()
    expect(page.locator("#uploadPanel")).to_be_hidden()
