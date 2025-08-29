# SRT Subtitle Translator

A web application for translating SRT subtitle files between languages using Google Translate, built with Flask and a modern HTML/JS frontend.

## Features
- Upload SRT subtitle files and translate them to another language
- Preserves subtitle timing and formatting
- Supports many major languages
- Download translated SRT files
- Modern, responsive web UI
- RESTful API endpoints
- CORS support for frontend-backend integration
- Error handling and logging

<img width="2549" height="1328" alt="image" src="https://github.com/user-attachments/assets/70f173d9-b681-4f9a-8e7f-ae934e24b0a4" />

## Requirements
- Python 3.8+
- Flask
- Flask-CORS
- googletrans (4.0.2 or compatible async version)

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
   pip install flask flask-cors googletrans==4.0.2 pytest
   ```


## Usage

### 1. Start the Flask backend (API server):
```
python venv/app.py
```
The API will be available at http://localhost:5000

### 2. Serve the frontend (index.html) with a static file server:
From the `srt-translator` directory, run:
```
python -m http.server 8080
```
This will serve your frontend files at http://localhost:8080/

Now you can open [http://localhost:8080/index.html](http://localhost:8080/index.html) in your browser to use the web interface.

**Note:**
- The backend (Flask) and frontend (static server) are separate. The frontend makes API requests to the backend.
- If you want to use a different port or path, adjust the commands and URLs accordingly.

## API Endpoints
- `GET /api/health` — Health check
- `GET /api/languages` — List supported languages
- `POST /api/translate` — Translate SRT file (multipart form: `srtFile`, `sourceLanguage`, `targetLanguage`)
- `GET /api/download/<file_id>` — Download translated SRT file

## Automated Tests
From the `srt-translator` directory, run:
```
python -m pytest -q
```

If you see "pytest is not recognized", install it into your current environment and try again:
```
python -m pip install -U pytest
python -m pytest -q
```

Notes for tests:
- You do NOT need to start the Flask app or a static file server to run tests. The tests use Flask's in-process test client.

## Project Structure
```
srt-translator/
├── index.html                       # Frontend web UI
├── venv/
│   └── app.py                       # Flask backend
├── requirements.txt                 # (optional) Python dependencies
└── tests/                           # Unit tests
    ├── conftest.py                  # pytest configuration
    ├── test_errors.py               # Error handling tests
    ├── test_health_and_languages.py # Health and languages endpoints tests
    └── test_translate_and_download.py # Translate and download flow tests
```

## Notes
- The backend stores translated files temporarily for download and cleans them up after a few minutes.
- For production, use a WSGI server (e.g., Gunicorn) and secure the API.
- You can extend the app to support more formats, authentication, or other translation providers.

## License
MIT License
