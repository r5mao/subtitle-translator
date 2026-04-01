---
name: Keep search UI and preview enhancement
overview: "Done: preserve search UI after translate + language card. Remaining: TMDb backdrop preview, rich preview (POST + translate/pinyin)."
todos:
  - id: preserve-ui-language-card
    content: "Sections 1–2: releaseFetchedAfterTranslate, language card/grid/details"
    status: completed
  - id: tmdb-backdrop-preview
    content: "Section 3: backdropUrl on rows, preview img prefers backdrop"
    status: completed
  - id: preview-post-translate-text
    content: "Section 4: POST preview with original/translated/pinyin + frontend overlay"
    status: completed
  - id: verify-preview-plan
    content: "Section 5: full verification after 3–4 ship"
    status: completed
isProject: false
---

# Keep search UI after translate, language card redesign, scene preview, rich subtitle preview

**Progress:** Items **1** and **2** are implemented in the repo (`releaseFetchedAfterTranslate`, `scrollIntoView` `block: 'nearest'`, `.language-card`, grid, toggle pill, `<details>` for dual). **3** and **4** are still to do.

---

## 1. Keep search results and preview after translate — **DONE**

**Cause:** `[static/js/main.js](static/js/main.js)` `runTranslation` success block cleared OpenSubtitles state and called `clearOpenSubtitlesSelection()`, which ran `hideSubtitlePreview()`.

**Implemented:**

- `releaseFetchedAfterTranslate()`: null `fetchedId`, `selectedOsFileId`, `fetchInProgressFileId`, `fetchedLabel`; does **not** hide preview or clear results; calls `validateLanguages()` and `filterAndRenderResults()`.
- Post-success search handling calls `releaseFetchedAfterTranslate()` only (no wiping `rawSearchResults` / table / chips / pager).
- `downloadSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' })`.

---

## 2. Language section redesign — **DONE**

**Implemented:**

- `#languageSection` wrapped in `**.language-card`** with title “Languages” and subtitle line.
- `**.language-grid`** for Original | Target; responsive single column; `:has(.translate-only-fields[hidden])` collapses to source-only when translate is off.
- Full-width `**.language-toggle-pill**` for “Translate to another language”.
- `**<details class="language-advanced">**` for dual output option.

Files: `[index.html](index.html)`, `[static/css/styles.css](static/css/styles.css)`.

---

## 3. Preview background: scene-style still, not portrait poster — **TODO**

**Goal:** Use a **widescreen still** that reads as a “scene” rather than a vertical poster.

**Reality check:** Neither OpenSubtitles nor this app extracts a frame at subtitle timecode; true video frames would require a separate pipeline (out of scope). The practical upgrade is **TMDb backdrops** (or similar wide stills from the same `images` API already used for posters).

**Backend:** In `[srt_translator/services/opensubtitles_client.py](srt_translator/services/opensubtitles_client.py)`:

- From the existing TMDb `movie/{id}/images` (and TV) response, read `**backdrops`** (not only `posters`).
- Pick the first (or first landscape) backdrop `file_path`; build URL e.g. `https://image.tmdb.org/t/p/w780{file_path}` (w780 fits 16:9 preview).
- Add `**backdropUrl`** on each flattened row when `tmdb_id` resolution runs (reuse a **single** images fetch per id where possible so poster + backdrop do not double-call the API).
- Keep `**posterUrl`** for table thumbnails; use `**backdropUrl`** in the subtitle preview when present, else fall back to `posterUrl`.

**Frontend:** `[static/js/main.js](static/js/main.js)` `refreshSubtitlePreview(row)` should prefer `normalizeHttpUrl(row.backdropUrl)` for the preview `<img>`, then `row.posterUrl`. `[index.html](index.html)` / CSS: rename classes from `subtitle-preview-poster` to something neutral (e.g. `subtitle-preview-bg`) if desired (cosmetic).

**Proxy:** `[opensubtitles_routes.py](srt_translator/api/opensubtitles_routes.py)` poster-image allowlist already includes `image.tmdb.org`.

---

## 4. Preview text: original, translation, and pinyin when applicable — **TODO**

**Current behavior:** `[GET /api/opensubtitles/fetched/<id>/preview](srt_translator/api/opensubtitles_routes.py)` returns only `**sampleLines`** from the **source** file’s first cue. It cannot show translation, dual stacking, or pinyin.

**Goal:** When the user has **translate** enabled, the overlay should mirror what the output will look like: **original** (and **translated** line(s)); for **pinyin** targets and **dual** mode, match the combinations used in `[translate_srt](srt_translator/api/__init__.py)` (SRT/ASS paths: dual + pinyin, pinyin-only, dual-only, etc.).

**Approach:**

1. **Change preview to `POST`** `/api/opensubtitles/fetched/<id>/preview` with JSON body, e.g.
  `{ "sourceLanguage", "targetLanguage", "dualLanguage", "wantsTranslate" }`  
   (align names with the UI). Keep **GET** as a thin compatibility layer that returns **original-only** `sampleLines` if you want to avoid breaking callers, or migrate tests and JS to POST only.
2. **Server:** After parsing the first cue (same as today), if `wantsTranslate` is false, return original lines only (and optional `layout: "single"`).
3. If `wantsTranslate` is true: build the **same text batches** as translate does for that first entry (per format SRT/ASS/SUB), call existing `**translation_service.translate_texts`** (or the same helper the translate route uses) for the minimal batch, then apply `**is_pinyin_target`**, `**line_to_pinyin**`, and **dual** composition to produce **plain-text preview strings** (strip ASS override tags for JSON; use `\n` between stacked lines for the UI).
4. **Response shape** (example; adjust to what the UI needs):
  - `originalDisplay`: string or list of lines (top block).  
  - `translatedDisplay`: string or list (middle/bottom).  
  - `pinyinDisplay`: optional string or list when pinyin is on.  
   Or a single ordered list `stackedLines` with explicit roles. The important part is the **UI can render the same stacking order** as the downloaded file.
5. **Frontend:** `[refreshSubtitlePreview](static/js/main.js)` should POST current `sourceLanguage`, `targetLanguage`, `dualLanguage`, and `wantsTranslate` (`translateToOtherLang.checked`). Add **multiple overlay elements** (or one block with line breaks) for original / translation / pinyin. **Debounce** or cancel in-flight requests when the user changes languages quickly.
6. **Tests:** Extend `[tests/test_opensubtitles.py](tests/test_opensubtitles.py)`: mock translator for preview POST; assert structure includes translated/pinyin fields when flags demand it; keep a test for original-only.
7. **Errors / perf:** If translation fails for preview, fall back to original-only lines and optional error hint in UI (non-blocking).

---

## 5. Verification — **PARTIAL** (re-run after 3–4)

**Already satisfied (from 1–2):**

- After translate: results table, chips, pager, preview **remain**; `fetchedId` cleared so re-download original requires re-select.
- Language card: cleaner hierarchy; advanced dual option in `<details>`.

**After implementing 3–4:**

- Preview image: prefers **backdrop** when `backdropUrl` present.
- With translate + dual + zh pinyin target: preview shows **original + translated + pinyin** consistent with export rules.

---

## Files (expected)


| Area            | Files                                                                                                                                       |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| JS              | `[static/js/main.js](static/js/main.js)`                                                                                                    |
| HTML            | `[index.html](index.html)`                                                                                                                  |
| CSS             | `[static/css/styles.css](static/css/styles.css)`                                                                                            |
| OS client       | `[srt_translator/services/opensubtitles_client.py](srt_translator/services/opensubtitles_client.py)`                                        |
| API             | `[srt_translator/api/opensubtitles_routes.py](srt_translator/api/opensubtitles_routes.py)`                                                  |
| Translate reuse | `[srt_translator/api/__init__.py](srt_translator/api/__init__.py)` or small shared module for “first cue preview” to avoid huge duplication |
| Tests           | `[tests/test_opensubtitles.py](tests/test_opensubtitles.py)`                                                                                |


