#!/usr/bin/env python3
"""
Capture README screenshots (requires: pip install playwright && playwright install chromium).
Starts Flask on 127.0.0.1:8765 in a background thread, then saves PNGs under docs/images/.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"


def _run_flask() -> None:
    sys.path.insert(0, str(ROOT))
    from srt_translator import create_app

    app = create_app()
    app.run(host="127.0.0.1", port=8765, use_reloader=False, debug=False, threaded=True)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Install Playwright: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 1

    IMAGES.mkdir(parents=True, exist_ok=True)

    t = threading.Thread(target=_run_flask, daemon=True)
    t.start()
    for _ in range(50):
        try:
            import urllib.request

            urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=0.5)
            break
        except OSError:
            time.sleep(0.1)
    else:
        print("Flask did not become ready on :8765", file=sys.stderr)
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto("http://127.0.0.1:8765/", wait_until="networkidle", timeout=60000)
            time.sleep(0.5)
            page.screenshot(path=str(IMAGES / "ui-desktop.png"), full_page=True)

            page.set_viewport_size({"width": 420, "height": 860})
            page.goto("http://127.0.0.1:8765/", wait_until="networkidle", timeout=60000)
            time.sleep(0.5)
            page.screenshot(path=str(IMAGES / "ui-mobile.png"), full_page=True)
        finally:
            browser.close()

    print("Wrote:", IMAGES / "ui-desktop.png", IMAGES / "ui-mobile.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
