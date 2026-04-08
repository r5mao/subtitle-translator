"""Client-side validation: error banner and disabled translate where applicable."""

import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_search_without_selection_blocks_translate(page, base_url: str) -> None:
    """No fetch yet: UI disables the button (click handler error banner is not used)."""
    page.goto(base_url, wait_until="domcontentloaded")
    expect(page.locator("#sourceSearch")).to_be_checked()

    expect(page.locator("#translateBtn")).to_be_disabled()
    expect(page.locator("#errorMessage")).to_be_hidden()


def test_upload_without_file_blocks_translate(page, base_url: str) -> None:
    """No file chosen: UI disables the button (same as search-without-selection)."""
    page.goto(base_url, wait_until="domcontentloaded")

    page.locator("#sourceUpload").check()
    expect(page.locator("#uploadPanel")).to_be_visible()

    expect(page.locator("#translateBtn")).to_be_disabled()
    expect(page.locator("#errorMessage")).to_be_hidden()


def test_same_source_and_target_shows_error(page, base_url: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded")

    page.locator("#sourceLanguage").select_option("en")
    page.locator("#targetLanguage").select_option("en")

    expect(page.locator("#errorMessage")).to_be_visible()
    expect(page.locator("#errorMessage")).to_contain_text(
        "Source and target languages cannot be the same."
    )
    expect(page.locator("#translateBtn")).to_be_disabled()
