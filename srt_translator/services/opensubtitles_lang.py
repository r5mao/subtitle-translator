"""Map app / GoogleTrans UI language codes to OpenSubtitles.com `languages` query values."""

# OpenSubtitles uses BCP-like codes (see GET /infos/languages). Mismatch fixes:
UI_TO_OPENSUBTITLES_LANG = {
    "pt": "pt-pt,pt-br",  # ambiguous "Portuguese" — search both
    "no": "no",  # OS uses "no" for Norwegian
    "zh-cn": "zh-cn",
    "zh-tw": "zh-tw",
    "zh-cn-pinyin": "zh-cn",
    "zh-tw-pinyin": "zh-tw",
}


def ui_lang_to_opensubtitles(ui_code: str) -> str:
    """Return comma-separated OS language codes for API `languages` param, or '' for any."""
    if not ui_code:
        return ""
    return UI_TO_OPENSUBTITLES_LANG.get(ui_code, ui_code)
