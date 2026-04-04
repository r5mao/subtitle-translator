# Browser E2E tests

Run (from repo root, after `pip install -r requirements.txt` and `playwright install chromium`):

```bash
python -m pytest e2e -q --browser chromium
```

Default `python -m pytest -q` does **not** collect this folder (`pytest.ini` sets `testpaths = tests`).

## OpenSubtitles and rate limits

These tests replace `OpenSubtitlesClient` with an in-process stub (`e2e/conftest.py`): **no real API calls**, so no quota or rate-limit usage.

If you add optional tests against the live API later, mark them `@pytest.mark.live_opensubtitles`, keep them out of CI by default, and use narrow queries, minimal pagination, and shared fixtures (see project plan).

## Assertions

Prefer Playwright `getByRole` / `getByLabel` and checks on downloaded file text. Add `data-testid` in app code only when roles cannot target dynamic rows.
