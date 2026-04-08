"""Upload path: file → translate → download; parametrized output settings."""

import re

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("dual", [False, True], ids=["single_lang", "dual_lang"])
@pytest.mark.parametrize(
    "target_lang",
    ["zh-cn", "zh-cn-pinyin"],
    ids=["zh_cn", "zh_cn_pinyin"],
)
def test_upload_translate_download(
    page,
    base_url: str,
    sample_srt_path,
    target_lang: str,
    dual: bool,
) -> None:
    page.goto(base_url, wait_until="domcontentloaded")

    page.locator("#sourceUpload").check()
    expect(page.locator("#uploadPanel")).to_be_visible()

    page.locator("#srtFile").set_input_files(str(sample_srt_path))

    page.locator("#sourceLanguage").select_option("en")
    page.locator("#targetLanguage").select_option(target_lang)
    page.locator("details.language-advanced summary").click()
    page.locator("#dualLanguage").set_checked(dual, force=True)

    page.get_by_role("button", name=re.compile(r"Translate subtitles")).click()
    page.get_by_role("button", name="Confirm").click()

    expect(page.get_by_text("Translation completed successfully")).to_be_visible(
        timeout=120_000
    )
    download_link = page.get_by_role(
        "link", name=re.compile(r"Download translated subtitle")
    )

    with page.expect_download(timeout=120_000) as dl:
        download_link.click()
    path = dl.value.path()
    assert path is not None
    text = path.read_text(encoding="utf-8")

    assert "你好，世界" in text
    assert "你好吗？" in text

    if target_lang == "zh-cn-pinyin":
        assert "Dialogue:" in text
        assert "nǐ" in text and "hǎo" in text
    else:
        assert "00:00:01" in text

    if dual:
        assert "Hello world" in text
        assert "How are you?" in text
