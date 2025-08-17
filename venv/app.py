import threading
# In-memory progress store (for demo; use Redis or similar for production)
translation_progress = {}
#!/usr/bin/env python3
"""
SRT Subtitle Translation Flask Backend

This Flask application provides a complete backend service for translating SRT subtitle files.
It handles file uploads, parses SRT format, translates text content while preserving timing,
and returns properly formatted translated SRT files.

Key Features:
- SRT file parsing with robust error handling
- Google Translate integration for multi-language support  
- Timing preservation during translation
- RESTful API endpoints
- CORS support for web frontend integration
- Comprehensive error handling and logging
"""

from flask import Flask, request, jsonify, send_file, stream_with_context, Response
from flask_cors import CORS
import asyncio
from googletrans import Translator
import re
import os
import tempfile
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import uuid

# Configure logging for debugging and monitoring
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask application with CORS support
app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing for web frontend


class SRTEntry:
    """
    Represents a single subtitle entry in an SRT file.
    
    Each SRT entry contains:
    - sequence_number: The numerical order of the subtitle
    - start_time: When the subtitle should appear (HH:MM:SS,mmm format)
    - end_time: When the subtitle should disappear
    - text_lines: List of text lines for this subtitle entry
    """
    
    def __init__(self, sequence_number: int, start_time: str, end_time: str, text_lines: List[str]):
        self.sequence_number = sequence_number
        self.start_time = start_time
        self.end_time = end_time
        self.text_lines = text_lines
    
    def to_srt_format(self) -> str:
        """
        Converts this entry back to standard SRT format.
        
        SRT format structure:
        1. Sequence number
        2. Time range (start --> end)
        3. Subtitle text (can be multiple lines)
        4. Blank line separator
        """
        text_content = '\n'.join(self.text_lines)
        return f"{self.sequence_number}\n{self.start_time} --> {self.end_time}\n{text_content}\n"



class SubtitleParser:
    """
    Handles parsing and processing of SRT, ASS, SSA, and SUB subtitle files.
    """
    @staticmethod
    def detect_format(content: str) -> str:
        if re.search(r'^\d+\s*\n\d{2}:\d{2}:\d{2},\d{3}\s*-->', content, re.MULTILINE):
            return 'srt'
        if '[Script Info]' in content and '[Events]' in content:
            return 'ass'
        if re.search(r'^Dialogue:', content, re.MULTILINE):
            return 'ass'
        if re.search(r'^\{\d+\}\{\d+\}', content, re.MULTILINE):
            return 'sub'
        return 'unknown'

    @staticmethod
    def parse(content: str) -> tuple:
        fmt = SubtitleParser.detect_format(content)
        if fmt == 'srt':
            return 'srt', SubtitleParser.parse_srt(content)
        elif fmt == 'ass':
            return 'ass', SubtitleParser.parse_ass(content)
        elif fmt == 'sub':
            return 'sub', SubtitleParser.parse_sub(content)
        else:
            raise ValueError('Unsupported or unknown subtitle format')

    @staticmethod
    def parse_srt(content: str) -> list:
        entries = []
        blocks = re.split(r'\n\s*\n', content.strip())
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            try:
                sequence_number = int(lines[0].strip())
                timing_pattern = r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})'
                timing_match = re.match(timing_pattern, lines[1].strip())
                if not timing_match:
                    continue
                start_time = timing_match.group(1)
                end_time = timing_match.group(2)
                text_lines = [line.strip() for line in lines[2:] if line.strip()]
                entries.append({'sequence_number': sequence_number, 'start_time': start_time, 'end_time': end_time, 'text_lines': text_lines})
            except Exception:
                continue
        return entries

    @staticmethod
    def parse_ass(content: str) -> list:
        # Only translate Dialogue lines, keep all others as-is
        lines = content.splitlines()
        parsed = []
        for idx, line in enumerate(lines):
            if line.startswith('Dialogue:'):
                parts = line.split(',', 9)
                if len(parts) >= 10:
                    text = parts[9]
                    parsed.append({'idx': idx, 'line': line, 'parts': parts, 'text': text})
        return {'lines': lines, 'dialogues': parsed}

    @staticmethod
    def parse_sub(content: str) -> list:
        # MicroDVD SUB: {start}{end}Text
        lines = content.splitlines()
        parsed = []
        for idx, line in enumerate(lines):
            m = re.match(r'\{(\d+)\}\{(\d+)\}(.*)', line)
            if m:
                parsed.append({'idx': idx, 'line': line, 'start': m.group(1), 'end': m.group(2), 'text': m.group(3)})
        return {'lines': lines, 'subs': parsed}

    @staticmethod
    def to_srt(entries: list) -> str:
        srt_content = []
        for entry in entries:
            srt_content.append(f"{entry['sequence_number']}\n{entry['start_time']} --> {entry['end_time']}\n" + '\n'.join(entry['text_lines']) + '\n')
        return '\n'.join(srt_content)

    @staticmethod
    def to_ass(parsed: dict, translated_texts: list) -> str:
        lines = parsed['lines'][:]
        for i, d in enumerate(parsed['dialogues']):
            parts = d['parts'][:]
            parts[9] = translated_texts[i]
            lines[d['idx']] = ','.join(parts)
        return '\n'.join(lines)

    @staticmethod
    def to_sub(parsed: dict, translated_texts: list) -> str:
        lines = parsed['lines'][:]
        for i, d in enumerate(parsed['subs']):
            lines[d['idx']] = f"{{{d['start']}}}{{{d['end']}}}{translated_texts[i]}"
        return '\n'.join(lines)


class TranslationService:
    """
    Handles text translation using Google Translate API (async/await with Translator from googletrans 4.0.2).
    """
    def __init__(self):
        self.language_names = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'zh-cn': 'Chinese (Simplified)',
            'zh-tw': 'Chinese (Traditional)',
            'ja': 'Japanese',
            'ko': 'Korean',
            'ar': 'Arabic',
            'hi': 'Hindi',
            'nl': 'Dutch',
            'sv': 'Swedish',
            'da': 'Danish',
            'no': 'Norwegian',
            'fi': 'Finnish',
            'pl': 'Polish',
            'tr': 'Turkish',
            'he': 'Hebrew'
        }


    async def translate_texts(self, texts: list, source_lang: str, target_lang: str, translator: Translator) -> list:
        # Preprocess all texts
        cleaned_texts = [self._preprocess_subtitle_text(t) if t.strip() else t for t in texts]
        # Prepare a mask for empty lines
        is_empty = [not t.strip() for t in texts]
        # Only translate non-empty lines
        to_translate = [t for t in cleaned_texts if t.strip()]
        if not to_translate:
            return texts
        # Batch translate
        results = await translator.translate(to_translate, src=source_lang, dest=target_lang)
        # googletrans returns a list if input is a list
        if isinstance(results, list):
            translated = [self._postprocess_subtitle_text(r.text) if hasattr(r, 'text') else '' for r in results]
        else:
            translated = [self._postprocess_subtitle_text(results.text)]
        # Reconstruct the output, preserving empty lines
        output = []
        idx = 0
        for empty, orig in zip(is_empty, texts):
            if empty:
                output.append(orig)
            else:
                output.append(translated[idx])
                idx += 1
        return output

    async def translate_subtitle_entries(self, entries: List[SRTEntry], source_lang: str, target_lang: str) -> List[SRTEntry]:
        # googletrans does not expose a list_operation_max_concurrency parameter.
        # The optimal batch size for translation is typically 50-100 lines per request.
        # googletrans handles batching internally, but too large batches may hit rate limits or slow down.
        # For best performance and reliability, keep batches <= 100 lines.
        translated_entries = []
        total_entries = len(entries)
        logger.info(f"Starting batch translation of {total_entries} entries from {source_lang} to {target_lang}")
        async with Translator() as translator:
            # Collect all lines to translate, preserving entry/line structure
            all_lines = []
            entry_line_counts = []
            for entry in entries:
                entry_line_counts.append(len(entry.text_lines))
                all_lines.extend(entry.text_lines)
            # Batch translate all lines (<=100 lines per batch)
            batch_size = 100
            translated_lines = []
            for i in range(0, len(all_lines), batch_size):
                batch = all_lines[i:i+batch_size]
                translated_batch = await self.translate_texts(batch, source_lang, target_lang, translator)
                translated_lines.extend(translated_batch)
            # Reconstruct entries
            idx = 0
            for entry, line_count in zip(entries, entry_line_counts):
                lines = translated_lines[idx:idx+line_count]
                translated_entry = SRTEntry(
                    entry.sequence_number,
                    entry.start_time,
                    entry.end_time,
                    lines
                )
                translated_entries.append(translated_entry)
                idx += line_count
                if (entry.sequence_number % 10 == 0) or (entry == entries[-1]):
                    logger.info(f"Translated entry {entry.sequence_number}/{total_entries}")
        logger.info(f"Batch translation completed successfully")
        return translated_entries

    def _preprocess_subtitle_text(self, text: str) -> str:
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _postprocess_subtitle_text(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        return text


# Initialize translation service
translation_service = TranslationService()

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint to verify service availability.
    
    Returns:
        JSON response indicating service status
    """
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'SRT Translation API'
    })

@app.route('/api/languages', methods=['GET'])
def get_supported_languages():
    """
    Returns list of supported languages for translation.
    
    Returns:
        JSON response with language codes and names
    """
    return jsonify({
        'languages': translation_service.language_names,
        'count': len(translation_service.language_names)
    })

@app.route('/api/task', methods=['GET'])
def get_task_id():
    """
    Returns task_id.
    
    Returns:
        JSON response with task_id
    """
    task_id = str(uuid.uuid4())
    logger.info(f"Get task ID: {task_id}")

    return jsonify({
        'ok': True,
        'taskId': task_id
    })

@app.route('/api/translate', methods=['POST'])
def translate_srt():
    """
    Main endpoint for translating SRT files.
    
    Expected form data:
    - srtFile: The SRT file to translate
    - sourceLanguage: Source language code
    - targetLanguage: Target language code
    
    Returns:
        JSON response with download URL or error message
    """

    # Validate request
    if 'srtFile' not in request.files:
        return jsonify({'error': 'No SRT file provided'}), 400
    if 'sourceLanguage' not in request.form or 'targetLanguage' not in request.form:
        return jsonify({'error': 'Source and target languages required'}), 400
    srt_file = request.files['srtFile']
    source_lang = request.form['sourceLanguage']
    target_lang = request.form['targetLanguage']
    dual_language = request.form.get('dualLanguage', 'false').strip().lower() in ('true', 'on', '1', 'yes')
    task_id = request.form['taskId']
    translation_progress[task_id] = {'progress': 0, 'status': 'started'}
    # Validate file
    if srt_file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    allowed_exts = ('.srt', '.ass', '.ssa', '.sub')
    if not srt_file.filename.lower().endswith(allowed_exts):
        return jsonify({'error': 'File must be a subtitle file (SRT, ASS, SSA, SUB)'}), 400
    # Validate languages
    if source_lang == target_lang:
        return jsonify({'error': 'Source and target languages cannot be the same'}), 400
    if source_lang not in translation_service.language_names:
        return jsonify({'error': f'Unsupported source language: {source_lang}'}), 400
    if target_lang not in translation_service.language_names:
        return jsonify({'error': f'Unsupported target language: {target_lang}'}), 400
    # Read and decode file content
    try:
        file_content = srt_file.read()
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        content = None
        for encoding in encodings:
            try:
                content = file_content.decode(encoding)
                logger.info(f"Successfully decoded file using {encoding} encoding")
                break
            except UnicodeDecodeError:
                continue
        if content is None:
            return jsonify({'error': 'Unable to decode file. Please ensure it\'s a valid text file.'}), 400
    except Exception as e:
        logger.error(f"Error reading file: {str(e)}")
        return jsonify({'error': 'Error reading file content'}), 400
    # Note translation start time
    translation_start_time = datetime.now()
    logger.info(f"Translation started at {translation_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    # Parse subtitle content (auto-detect format)
    try:
        original_filename = srt_file.filename
        base_name = os.path.splitext(original_filename)[0]
        fmt, parsed = SubtitleParser.parse(content)
        logger.info(f"Parsed subtitle file as format: {fmt}")
    except ValueError as e:
        logger.error(f"Subtitle parsing error: {str(e)}")
        return jsonify({'error': f'Invalid subtitle format: {str(e)}'}), 400
    # Translate and re-serialize
    try:
        # Start timing
        translation_timer_start = datetime.now()
        def update_progress(current, total):
            percent = int((current / total) * 100)
            translation_progress[task_id]['progress'] = percent
        if fmt == 'srt':
            def srt_progress(entries, source_lang, target_lang):
                translated_entries = []
                total_entries = len(entries)
                async def do_translate():
                    async with Translator() as translator:
                        all_lines = []
                        entry_line_counts = []
                        for entry in entries:
                            entry_line_counts.append(len(entry.text_lines))
                            all_lines.extend(entry.text_lines)
                        batch_size = 100
                        translated_lines = []
                        for i in range(0, len(all_lines), batch_size):
                            batch = all_lines[i:i+batch_size]
                            translated_batch = await translation_service.translate_texts(batch, source_lang, target_lang, translator)
                            translated_lines.extend(translated_batch)
                            update_progress(min(i+batch_size, len(all_lines)), len(all_lines))
                        idx = 0
                        for entry, line_count in zip(entries, entry_line_counts):
                            lines = translated_lines[idx:idx+line_count]
                            translated_entry = SRTEntry(
                                entry.sequence_number,
                                entry.start_time,
                                entry.end_time,
                                lines
                            )
                            translated_entries.append(translated_entry)
                            idx += line_count
                            update_progress(idx, len(all_lines))
                asyncio.run(do_translate())
                return translated_entries
            translated_entries = srt_progress([
                SRTEntry(e['sequence_number'], e['start_time'], e['end_time'], e['text_lines']) for e in parsed
            ], source_lang, target_lang)
            # If dual-language, include original lines above translated lines per entry
            if dual_language:
                output_entries = []
                for orig_dict, trans_entry in zip(parsed, translated_entries):
                    combined_lines = orig_dict['text_lines'] + trans_entry.text_lines
                    output_entries.append({
                        'sequence_number': trans_entry.sequence_number,
                        'start_time': trans_entry.start_time,
                        'end_time': trans_entry.end_time,
                        'text_lines': combined_lines
                    })
                translated_content = SubtitleParser.to_srt(output_entries)
            else:
                translated_content = SubtitleParser.to_srt([
                    {'sequence_number': e.sequence_number, 'start_time': e.start_time, 'end_time': e.end_time, 'text_lines': e.text_lines}
                    for e in translated_entries
                ])
            translated_filename = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.srt"
        elif fmt == 'ass':
            texts = [d['text'] for d in parsed['dialogues']]
            total_lines = len(texts)
            translated_texts = []
            async def do_translate_ass():
                async with Translator() as translator:
                    batch_size = 100
                    for i in range(0, total_lines, batch_size):
                        batch = texts[i:i+batch_size]
                        translated_batch = await translation_service.translate_texts(batch, source_lang, target_lang, translator)
                        translated_texts.extend(translated_batch)
                        update_progress(min(i+batch_size, total_lines), total_lines)
            asyncio.run(do_translate_ass())
            if dual_language:
                combined_texts = [f"{orig}\\N{tran}" for orig, tran in zip(texts, translated_texts)]
                translated_content = SubtitleParser.to_ass(parsed, combined_texts)
            else:
                translated_content = SubtitleParser.to_ass(parsed, translated_texts)
            translated_filename = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.ass"
        elif fmt == 'sub':
            texts = [d['text'] for d in parsed['subs']]
            total_lines = len(texts)
            translated_texts = []
            async def do_translate_sub():
                async with Translator() as translator:
                    batch_size = 100
                    for i in range(0, total_lines, batch_size):
                        batch = texts[i:i+batch_size]
                        translated_batch = await translation_service.translate_texts(batch, source_lang, target_lang, translator)
                        translated_texts.extend(translated_batch)
                        update_progress(min(i+batch_size, total_lines), total_lines)
            asyncio.run(do_translate_sub())
            if dual_language:
                combined_texts = [f"{orig}|{tran}" for orig, tran in zip(texts, translated_texts)]
                translated_content = SubtitleParser.to_sub(parsed, combined_texts)
            else:
                translated_content = SubtitleParser.to_sub(parsed, translated_texts)
            translated_filename = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.sub"
        else:
            raise ValueError('Unsupported subtitle format')
        translation_progress[task_id]['progress'] = 100
        logger.info(f"Translation completed for {fmt} format")
        # End timing
        translation_timer_end = datetime.now()
        translation_duration = translation_timer_end - translation_timer_start
        total_ms = int(translation_duration.total_seconds() * 1000)
        duration_minutes = total_ms // 60000
        duration_seconds = (total_ms % 60000) // 1000
        duration_ms = total_ms % 1000
        if duration_minutes:
            duration_str = f"{duration_minutes} mins {duration_seconds} seconds {duration_ms} ms"
        elif duration_seconds:
            duration_str = f"{duration_seconds} seconds {duration_ms} ms"
        else:
            duration_str = f"{duration_ms} ms"
        logger.info(f"Translation took {duration_str}")
        # Create temporary file for download
        file_id = str(uuid.uuid4())
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, f"{file_id}_{translated_filename}")
        with open(temp_file_path, 'w', encoding='utf-8') as temp_file:
            temp_file.write(translated_content)
        logger.info(f"Created translated file: {temp_file_path}")
        return jsonify({
            'success': True,
            'message': 'Translation completed successfully',
            'downloadUrl': f'/api/download/{file_id}',
            'filename': translated_filename,
            'sourceLanguage': translation_service.language_names.get(source_lang, source_lang),
            'targetLanguage': translation_service.language_names.get(target_lang, target_lang),
            'translationStartedAt': translation_start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'translationDuration': duration_str
            # 'taskId': task_id
        })
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        return jsonify({'error': f'Translation failed: {str(e)}'}), 500
    # ...existing code...

@app.route('/api/download/<file_id>', methods=['GET'])
def download_file(file_id):
    """
    Endpoint for downloading translated SRT files.
    
    Args:
        file_id: Unique identifier for the translated file
        
    Returns:
        File download response or error message
    """
    try:
        # Validate file_id format (should be a UUID)
        if not re.match(r'^[a-f0-9-]{36}$', file_id):
            return jsonify({'error': 'Invalid file ID'}), 400
        
        # Find the file in temp directory
        temp_dir = tempfile.gettempdir()
        matching_files = [f for f in os.listdir(temp_dir) if f.startswith(file_id)]
        
        if not matching_files:
            return jsonify({'error': 'File not found or expired'}), 404
        
        file_path = os.path.join(temp_dir, matching_files[0])
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # Extract original filename
        filename = matching_files[0].split('_', 1)[1]
        
        # Send file and schedule cleanup
        def cleanup_file():
            import threading
            import time
            def delayed_cleanup():
                time.sleep(300)  # Wait 5 minutes before cleanup
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Cleaned up temporary file: {file_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up file {file_path}: {str(e)}")
            
            cleanup_thread = threading.Thread(target=delayed_cleanup)
            cleanup_thread.daemon = True
            cleanup_thread.start()
        
        cleanup_file()
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='text/plain'
        )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({'error': 'Error downloading file'}), 500

@app.route('/api/translate/progress/<task_id>')
def sse_translation_progress(task_id):
    import time
    @stream_with_context
    def event_stream():
        last_progress = -1
        while True:
            progress = translation_progress.get(task_id, {}).get('progress', 0)
            if progress != last_progress:
                yield f"data: {progress}\n\n"
                last_progress = progress
            if progress >= 100:
                break
            time.sleep(0.5)
    # Add CORS and disable caching for SSE
    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*',
        'X-Accel-Buffering': 'no'  # For nginx, disables response buffering
    }
    return Response(event_stream(), headers=headers)

@app.errorhandler(413)
def file_too_large(error):
    """Handle file size limit exceeded errors."""
    return jsonify({'error': 'File too large. Maximum size is 16MB.'}), 413

@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors."""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(404)
def not_found(error):
    """Handle not found errors."""
    return jsonify({'error': 'Endpoint not found'}), 404

if __name__ == '__main__':
    # Set maximum file size (16MB)
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    
    # Development server configuration
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )

"""
Installation Requirements:
pip install flask flask-cors googletrans==4.0.0rc1

Usage:
1. Save this file as app.py
2. Install required packages
3. Run: python app.py
4. The API will be available at http://localhost:5000

API Endpoints:
- GET /api/health - Health check
- GET /api/languages - Get supported languages
- GET /api/task - Get task ID
- POST /api/translate - Translate SRT file
- GET /api/download/<file_id> - Download translated file

For production deployment, consider:
- Using a proper WSGI server like Gunicorn
- Implementing rate limiting
- Adding authentication if needed
- Using a proper file storage solution
- Implementing proper logging and monitoring
"""
# End of app.py