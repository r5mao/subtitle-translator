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

from flask import Flask, request, jsonify, send_file
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
            'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'it': 'Italian', 'pt': 'Portuguese', 'ru': 'Russian', 'zh': 'Chinese',
            'ja': 'Japanese', 'ko': 'Korean', 'ar': 'Arabic', 'hi': 'Hindi',
            'nl': 'Dutch', 'sv': 'Swedish', 'da': 'Danish', 'no': 'Norwegian',
            'fi': 'Finnish', 'pl': 'Polish', 'tr': 'Turkish', 'he': 'Hebrew'
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
            # Batch translate all lines
            translated_lines = await self.translate_texts(all_lines, source_lang, target_lang, translator)
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


# ...existing code...

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
    try:
        # Validate request
        if 'srtFile' not in request.files:
            return jsonify({'error': 'No SRT file provided'}), 400
        
        if 'sourceLanguage' not in request.form or 'targetLanguage' not in request.form:
            return jsonify({'error': 'Source and target languages required'}), 400
        
        srt_file = request.files['srtFile']
        source_lang = request.form['sourceLanguage']
        target_lang = request.form['targetLanguage']
        
        # Validate file
        if srt_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not srt_file.filename.lower().endswith('.srt'):
            return jsonify({'error': 'File must be an SRT subtitle file'}), 400
        
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
            
            # Try different encodings to handle various file formats
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
            if fmt == 'srt':
                translated_entries = asyncio.run(
                    translation_service.translate_subtitle_entries([
                        SRTEntry(e['sequence_number'], e['start_time'], e['end_time'], e['text_lines']) for e in parsed
                    ], source_lang, target_lang)
                )
                translated_content = SubtitleParser.to_srt([
                    {'sequence_number': e.sequence_number, 'start_time': e.start_time, 'end_time': e.end_time, 'text_lines': e.text_lines}
                    for e in translated_entries
                ])
                translated_filename = f"{base_name}_{target_lang}.srt"
            elif fmt == 'ass':
                texts = [d['text'] for d in parsed['dialogues']]
                translated_texts = asyncio.run(
                    translation_service.translate_texts(texts, source_lang, target_lang, Translator())
                )
                translated_content = SubtitleParser.to_ass(parsed, translated_texts)
                translated_filename = f"{base_name}_{target_lang}.ass"
            elif fmt == 'sub':
                texts = [d['text'] for d in parsed['subs']]
                translated_texts = asyncio.run(
                    translation_service.translate_texts(texts, source_lang, target_lang, Translator())
                )
                translated_content = SubtitleParser.to_sub(parsed, translated_texts)
                translated_filename = f"{base_name}_{target_lang}.sub"
            else:
                raise ValueError('Unsupported subtitle format')
            logger.info(f"Translation completed for {fmt} format")
        except Exception as e:
            logger.error(f"Translation error: {str(e)}")
            return jsonify({'error': f'Translation failed: {str(e)}'}), 500
        
        # Create temporary file for download
        try:
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
                'targetLanguage': translation_service.language_names.get(target_lang, target_lang)
            })
        except Exception as e:
            logger.error(f"File creation error: {str(e)}")
            return jsonify({'error': 'Error creating download file'}), 500
    
    except Exception as e:
        logger.error(f"Unexpected error in translate_srt: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

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