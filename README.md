# SRT Subtitle Translator

A web application for translating subtitle files between languages using Google Translate, built with Flask and a vanilla HTML/JS frontend.

## Features
- Upload subtitle files (**SRT**, **ASS/SSA**, **SUB**) and translate them to another language
- Preserves subtitle timing and formatting
- Supports many major languages (including Chinese + Pinyin target options)
- Download translated files
- Modern, responsive web UI
- RESTful API endpoints
- CORS support for frontend-backend integration
- Error handling and logging

<img width="2549" height="1328" alt="image" src="https://github.com/user-attachments/assets/70f173d9-b681-4f9a-8e7f-ae934e24b0a4" />

## Requirements
- Python 3.8+ (**googletrans 4.0.2** uses current `httpx` and does not need the old stdlib `cgi` module)
- Dependencies are pinned in `requirements.txt` (Flask, Flask-CORS, **googletrans 4.0.2**, etc.)

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


## Usage

### 1. Start the Flask backend (API server):
```
python app.py
```
The API will be available at http://localhost:5000

### 2. Serve the frontend (optional static server):
If you do not rely on Flask’s root route alone, from the **project root** run:
```
python -m http.server 8080
```
Then open the app (or `index.html`) as you prefer.

**Note:**
- For development, Flask serves `index.html` at `/` and static assets under `/static/`. You can use **http://localhost:5000/** directly.
- If you use a separate static server on another port, the frontend is configured to call the API at `http://localhost:5000` (see `static/js/main.js`).
- If you want a different port or host, adjust the URLs accordingly.

## API Endpoints
- `GET /api/health` — Health check
- `GET /api/languages` — List supported languages
- `POST /api/translate` — Translate subtitle file (multipart form: `srtFile`, `sourceLanguage`, `targetLanguage`, etc.)
- `GET /api/download/<file_id>` — Download translated file

## Automated Tests
From the project root, run:
```
python -m pytest -q
```

If you see "pytest is not recognized", install it into your current environment and try again:
```
python -m pip install -U pytest
python -m pytest -q
```

Notes for tests:
- You do **not** need to start the Flask app or a static file server to run tests. The tests use Flask’s in-process test client.

## Project Structure
```
project root/
├── app.py                 # Run the Flask app
├── index.html             # Frontend web UI
├── static/                 # CSS, JS, favicon
├── srt_translator/         # Flask app package (API, translation, parsers)
├── requirements.txt        # Pinned Python dependencies
└── tests/                  # Pytest suite
    ├── conftest.py
    ├── test_errors.py
    ├── test_health_and_languages.py
    └── test_translate_and_download.py
```

## Notes
- The backend stores translated files temporarily for download and cleans them up after a few minutes.
- For production, use a WSGI server (e.g., Gunicorn) and secure the API.
- You can extend the app to support more formats, authentication, or other translation providers.

## License
MIT License
