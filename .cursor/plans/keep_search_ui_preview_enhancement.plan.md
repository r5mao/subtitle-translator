---
name: ""
overview: ""
todos: []
isProject: false
---

# Keep search UI after translate, language card redesign, scene preview, rich subtitle preview

## 1. Keep search results and preview after translate (unchanged intent)

**Cause:** `[static/js/main.js](static/js/main.js)` `runTranslation` success block clears OpenSubtitles state and calls `clearOpenSubtitlesSelection()`, which runs `hideSubtitlePreview()`.

**Fix:**

- Add `releaseFetchedAfterTranslate()`: null `fetchedId`, `selectedOsFileId`, `fetchInProgressFileId`; clear `fetchedLabel`; **do not** hide preview or clear `rawSearchResults` / table / chips / pager.
- Replace the post-success `if (isSearchMode() && fetchedId) { clearOpenSubtitlesSelection(); rawSearchResults = []; ... }` block with only `releaseFetchedAfterTranslate()` when appropriate.
- Call `filterAndRenderResults()` if needed so row highlight drops (selection uses `fetchedId`).

**Optional:** `downloadSection.scrollIntoView({ block: 'nearest' })` to reduce jarring scroll.

---

## 2. Language section redesign (unchanged intent)

- Wrap `#languageSection` content in a **card** (padding, soft background, radius).
- **Heading** + one short helper line.
- **CSS grid** for Original | Target (1 column on small screens).
- **Full-width toggle** row for “Translate to another language” (checkbox or segmented control).
- Move **dual-language** checkbox into `<details>` “Advanced output options”.

Files: `[index.html](index.html)`, `[static/css/styles.css](static/css/styles.css)`; minimal `[static/js/main.js](static/js/main.js)` if wrappers change (keep existing element `id`s on controls).

---

## 3. Preview background: scene-style still, not portrait poster

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

## 4. Preview text: original, translation, and pinyin when applicable

**Current behavior:** `[GET /api/opensubtitles/fetched/<id>/preview](srt_translator/api/opensubtitles_routes.py)` returns only `**sampleLines`** from the **source** file’s first cue. It cannot show translation, dual stacking, or pinyin.

**Goal:** When the user has **translate** enabled, the overlay should mirror what the output will look like: **original** (and **translated** line(s)); for **pinyin** targets and **dual** mode, match the combinations used in `[translate_srt](srt_translator/api/__init__.py)` (SRT/ASS paths: dual + pinyin, pinyin-only, dual-only, etc.).

**Approach:**

1. **Change preview to `POST`** `/api/opensubtitles/fetched/<id>/preview` with JSON body, e.g.
  `{ "sourceLanguage", "targetLanguage", "dualLanguage", "wantsTranslate" }`  
   (align names with the UI). Keep **GET** as a thin compatibility layer that returns **original-only** `sampleLines` if you want to avoid breaking callers, or migrate tests and JS to POST only.
2. **Server:** After parsing the first cue (same as today), if `wantsTranslate` is false, return original lines only (and optional `layout: "single"`).
3. If `wantsTranslate` is true: build the **same text batches** as translate does for that first entry (per format SRT/ASS/SUB), call existing `**translation_service.translate_texts`** (or the same helper the translate route uses) for the minimal batch, then apply `**is_pinyin_target`**, `**line_to_pinyin`**, and **dual** composition to produce **plain-text preview strings** (strip ASS override tags for JSON; use `\n` between stacked lines for the UI).
4. **Response shape** (example; adjust to what the UI needs):
  - `originalDisplay`: string or list of lines (top block).  
  - `translatedDisplay`: string or list (middle/bottom).  
  - `pinyinDisplay`: optional string or list when pinyin is on.  
   Or a single ordered list `stackedLines` with explicit roles. The important part is the **UI can render the same stacking order** as the downloaded file.
5. **Frontend:** `[refreshSubtitlePreview](static/js/main.js)` should POST current `sourceLanguage`, `targetLanguage`, `dualLanguage`, and `wantsTranslate` (`translateToOtherLang.checked`). Add **multiple overlay elements** (or one block with line breaks) for original / translation / pinyin. **Debounce** or cancel in-flight requests when the user changes languages quickly.
6. **Tests:** Extend `[tests/test_opensubtitles.py](tests/test_opensubtitles.py)`: mock translator for preview POST; assert structure includes translated/pinyin fields when flags demand it; keep a test for original-only.
7. **Errors / perf:** If translation fails for preview, fall back to original-only lines and optional error hint in UI (non-blocking).

---

## 5. Verification

- After translate: results table, chips, pager, preview **remain**; `fetchedId` cleared so re-download original requires re-select.
- Preview image: prefers **backdrop** when `backdropUrl` present.
- With translate + dual + zh pinyin target: preview shows **original + translated + pinyin** consistent with export rules.
- Language card: cleaner hierarchy; advanced dual option tucked in details.

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


