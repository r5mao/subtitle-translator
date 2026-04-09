# Subtitle Translator

A web application for translating subtitle files between languages using Google Translate, built with Flask and a vanilla HTML frontend. UI scripts are written in **TypeScript** under `frontend/src/` and compiled to `static/js/` (`npm run build`).

## Features

- **Subtitle input (pick one):**
  - **Upload** **SRT**, **ASS/SSA**, or **SUB** files from disk, or
  - **Search [OpenSubtitles.com](https://www.opensubtitles.com/)** (optional) by movie/show title and select a subtitle file—no manual download step
- Preserves subtitle timing and formatting
- Supports many major languages (including Chinese + Pinyin target options)
- Download translated files
- Modern, responsive web UI
- RESTful API endpoints
- CORS support for frontend-backend integration
- Error handling and logging

## Screenshots


| Desktop (1280×900 viewport)       | Narrow / mobile-style (420px wide)     |
| --------------------------------- | -------------------------------------- |
| SRT Subtitle Translator — desktop | SRT Subtitle Translator — mobile width |


## Requirements

- Python 3.8+ (**googletrans 4.0.2** uses current `httpx` and does not need the old stdlib `cgi` module)
- Dependencies are pinned in `requirements.txt` (Flask, Flask-CORS, **googletrans 4.0.2**, python-dotenv, etc.)
- **Node.js** (current LTS is fine) only if you change the frontend: TypeScript is compiled with `npm run build` into `static/js/`. Running the app from an existing clone uses the committed JS output without Node.

## Installation

1. Clone this repository or copy the project files.
2. Create and activate a virtual environment (recommended):
  ```
   python -m venv venv

   # On Windows:
   venv\Scripts\activate

   # On Mac/Linux:
   source venv/bin/activate
  ```
3. Install dependencies:
  ```
   pip install -r requirements.txt
  ```
4. If you edit `**frontend/src/**`, install JS tooling and rebuild the browser bundle:
  ```
   npm ci
   npm run build
  ```
   This writes ES modules and source maps into `static/js/`. Use `npm run typecheck` for `tsc --noEmit` only.

## Configuration (optional OpenSubtitles)

Search-from-catalog is **off** until you add API credentials. Register at [OpenSubtitles.com](https://www.opensubtitles.com/), create an **API key**, and add a `.env` file in the **project root** (same folder as `app.py`):

```
OPENSUBTITLES_API_KEY=your_api_key_here
OPENSUBTITLES_USERNAME=your_opensubtitles_username
OPENSUBTITLES_PASSWORD=your_opensubtitles_password
```

Optional:

```
OPENSUBTITLES_USER_AGENT=YourAppName 1.0
```

**TMDb metadata (posters, titles, years):** If OpenSubtitles omits poster URLs or uses working titles (e.g. “Avatar 2”), set a [TMDb](https://www.themoviedb.org/settings/api) API key. The server calls TMDb **movie** or **TV** details by `tmdb_id` on each result and uses TMDb’s **title**, **release** / **first air** year, and poster/backdrop images when present:

```
TMDB_API_KEY=your_tmdb_v3_key
```

The app loads `.env` from the project root inside `create_app()`, so variables are available **even if your shell’s current directory is not the project folder**.

**Security:** Never expose these values in the browser or commit `.env` to git (it should stay in `.gitignore`).

## Usage

### 1. Start the Flask backend

```
python app.py
```

The app and API are available at **[http://localhost:5000/](http://localhost:5000/)** (Flask serves `index.html` at `/` and static files under `/static/`). This is the simplest way to run everything.

If translate shows **Failed to fetch**, the browser never reached Flask (wrong URL, page opened as `file://`, or **HTTPS** page calling **HTTP** API). Use the URL above or set the `subtitle-translator-api-base` meta tag to your Flask origin.

### 2. Optional: separate static server

If you serve the UI with something like `python -m http.server 8080` from the project root, open **[http://localhost:8080/](http://localhost:8080/)** (or your chosen port). The bundled `main.js` will send API requests to the **same hostname on port 5000** (e.g. `http://127.0.0.1:5000`) when the page is on common dev ports (8080, 5500, 3000) on `localhost` / `127.0.0.1`, as long as Flask is still running on port 5000.

To force a different API origin, uncomment and set the meta tag in `index.html`:

```html
<meta name="subtitle-translator-api-base" content="http://127.0.0.1:5000">
```

### OpenSubtitles UI (when configured)

- Choose **Search OpenSubtitles** or **Upload file**.
- Search uses the **Original Language** dropdown to filter subtitle language unless **Search all languages** is checked (title-only search, then use language chips in results).
- Press **Enter** in the title field to run the same search as the **Search subtitles** button (Enter does **not** start translation).
- Use **rows per page** and **Previous** / **Next** to page through OpenSubtitles results.
- After you **Select** a row, the app fetches that subtitle server-side. Click **Translate Subtitles**, confirm in the dialog, then translation runs (same pipeline as an upload).
- Search result posters are loaded through `**GET /api/opensubtitles/poster-image`** (same origin) so CDN hotlink limits are less likely to block thumbnails.

## API Endpoints


| Method | Path                                | Description                                                                                                                                                                                                                          |
| ------ | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET`  | `/api/health`                       | Health check                                                                                                                                                                                                                         |
| `GET`  | `/api/languages`                    | Supported translation languages                                                                                                                                                                                                      |
| `GET`  | `/api/task`                         | New UUID for translation progress (SSE)                                                                                                                                                                                              |
| `GET`  | `/api/opensubtitles/status`         | `{ "configured": true/false }` — credentials present                                                                                                                                                                                 |
| `GET`  | `/api/opensubtitles/poster-image`   | Query: `url` — HTTPS image URL (allowlisted hosts only); proxies bytes for UI thumbnails                                                                                                                                             |
| `POST` | `/api/opensubtitles/search`         | JSON: `query`, optional `language` (UI code), optional `page` (1–10 only), optional `perPage` (`10`, `25`, `50`, or `100`; default `10`). Response includes `results`, `page`, `perPage`, `totalPages` (capped at 10), `totalCount`. |
| `POST` | `/api/opensubtitles/fetch`          | JSON: `file_id` — downloads subtitle to a temp file, returns `fetchedId`                                                                                                                                                             |
| `POST` | `/api/translate`                    | Multipart: `sourceLanguage`, `targetLanguage`, `dualLanguage`, `taskId`, and **either** `srtFile` **or** `fetchedId`                                                                                                                 |
| `GET`  | `/api/translate/progress/<task_id>` | SSE progress                                                                                                                                                                                                                         |
| `GET`  | `/api/download/<file_id>`           | Download translated file                                                                                                                                                                                                             |


OpenSubtitles routes return **503** with a clear message if credentials are missing.

## Automated Tests

From the project root:

```
python -m pytest -q
```

This collects only the `**tests/**` package (see `pytest.ini`). You do **not** need to start Flask for those runs; they use Flask’s in-process client. OpenSubtitles calls are mocked where needed.

### Python style (Ruff)

Formatting and lint rules live in `**pyproject.toml`** ([Ruff](https://docs.astral.sh/ruff/): PEP 8–aligned, Black-compatible formatter). Install the dev extra and run from the project root:

```
python -m pip install -r requirements-dev.txt
python -m ruff format .
python -m ruff check .
```

**End-to-end (browser) tests** live in `**e2e/`** and are **not** run by the command above. They start a real Flask server on an ephemeral port with a **fake OpenSubtitles client** (no real API calls, no rate-limit use) and a **fake translator** matching the mapping in `tests/conftest.py`. Run them explicitly (build the frontend first so `static/js/` matches `frontend/src/`):

```
python -m pip install -r requirements.txt
npm ci
npm run build
playwright install chromium
python -m pytest e2e -q --browser chromium
```

If you see "pytest is not recognized":

```
python -m pip install -U pytest
python -m pytest -q
```

## Project Structure

```
project root/
├── app.py                          # Entry: run Flask
├── index.html                      # Frontend UI
├── frontend/src/                   # TypeScript sources (build → static/js/)
├── package.json                    # npm scripts: build, typecheck
├── tsconfig.json                   # tsc: ES modules → static/js/
├── docs/images/                    # README screenshots (regenerate via scripts/)
├── scripts/
│   └── capture_readme_screenshots.py
├── static/                         # CSS, compiled JS, favicon
├── srt_translator/
│   ├── __init__.py                 # create_app(), loads .env from project root
│   ├── config.py
│   ├── api/
│   │   ├── __init__.py             # translate, download, SSE, registers OS routes
│   │   └── opensubtitles_routes.py # OpenSubtitles proxy routes
│   └── services/
│       ├── translation.py
│       ├── subtitle_parser.py
│       ├── opensubtitles_client.py # Login, search, download (server-side)
│       └── opensubtitles_lang.py   # UI language → OpenSubtitles codes
├── e2e/                            # Browser E2E (pytest e2e); not run by default pytest
│   ├── conftest.py
│   ├── fixtures/
│   └── test_*.py
├── pyproject.toml                  # Ruff lint + format (Python style)
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt            # ruff (optional dev)
└── tests/
    ├── conftest.py
    ├── test_errors.py
    ├── test_health_and_languages.py
    ├── test_translate_and_download.py
    └── test_opensubtitles.py
```

## Notes

- The backend stores **fetched** OpenSubtitles files and **translated** outputs temporarily under the system temp directory; translated downloads are scheduled for cleanup after a few minutes. Fetched temp files are removed after a successful translate.
- OpenSubtitles has **rate limits and download quotas**; see their documentation and your account on opensubtitles.com.
- For production, use a WSGI server (e.g. Gunicorn), secure the API, and manage secrets via the environment or a secrets manager—not a committed `.env`.

## License

MIT License