"""API blueprint for SRT Translator."""
from flask import Blueprint, jsonify, request, send_file, Response, stream_with_context
from datetime import datetime
from srt_translator.services.translation import (
    google_translate_dest,
    is_pinyin_target,
    translation_service,
)
from srt_translator.services.pinyin_helper import line_to_pinyin
from srt_translator.services.subtitle_parser import SubtitleParser
from srt_translator.services.fetched_subtitle_file import (
    is_valid_fetched_id,
    resolve_fetched_subtitle_file,
)
from srt_translator.services.srt_entry import SRTEntry
import logging
import uuid
import os
import tempfile
import re
import asyncio

from googletrans import Translator

# Configure logging for debugging and monitoring
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

# In-memory progress store
translation_progress = {}


def _ass_escape_plain(s: str) -> str:
    return (s or '').replace('\\', '\\\\')


def _ass_english_line(text: str) -> str:
    return f"{{\\fs10}}{_ass_escape_plain(text)}{{\\r}}"


def _ass_chinese_line(text: str) -> str:
    return f"{{\\fs12}}{_ass_escape_plain(text)}{{\\r}}"


def _ass_pinyin_line(pinyin_plain: str) -> str:
    return f"{{\\fs8}}{_ass_escape_plain(pinyin_plain)}{{\\r}}"


def _join_srt_text_lines(lines: list) -> str:
    return ' '.join(x.strip() for x in (lines or []) if x.strip())


def _collapse_ass_dialogue(text: str) -> str:
    if not text:
        return ''
    return ' '.join(p.strip() for p in text.split(r'\N') if p.strip())


def _collapse_sub_text(text: str) -> str:
    if not text:
        return ''
    return ' '.join(p.strip() for p in re.split(r'[\r\n]+', text) if p.strip())

# Routes will be registered here
# @api_bp.route('/health')
# def health_check():
#     """Basic health check endpoint."""
#     return jsonify({'status': 'ok'})

@api_bp.route('/health', methods=['GET'])
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

@api_bp.route('/languages', methods=['GET'])
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

@api_bp.route('/task', methods=['GET'])
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

@api_bp.route('/translate', methods=['POST'])
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
    if 'sourceLanguage' not in request.form or 'targetLanguage' not in request.form:
        return jsonify({'error': 'Source and target languages required'}), 400
    source_lang = request.form['sourceLanguage']
    target_lang = request.form['targetLanguage']
    if source_lang == target_lang:
        return jsonify({'error': 'Source and target languages cannot be the same'}), 400
    if source_lang not in translation_service.language_names:
        return jsonify({'error': f'Unsupported source language: {source_lang}'}), 400
    if target_lang not in translation_service.language_names:
        return jsonify({'error': f'Unsupported target language: {target_lang}'}), 400
    google_dest = google_translate_dest(target_lang)
    use_pinyin = is_pinyin_target(target_lang)
    dual_language = request.form.get('dualLanguage', 'false').strip().lower() in ('true', 'on', '1', 'yes')
    task_id = request.form['taskId']
    translation_progress[task_id] = {'progress': 0, 'status': 'started'}

    fetched_id = request.form.get('fetchedId', '').strip()
    file_content = None
    original_filename = None
    fetched_temp_path = None

    if fetched_id:
        if not is_valid_fetched_id(fetched_id):
            return jsonify({'error': 'Invalid fetched subtitle id'}), 400
        resolved = resolve_fetched_subtitle_file(fetched_id)
        if not resolved:
            return jsonify({'error': 'Fetched subtitle expired or not found. Search and select again.'}), 404
        fetched_temp_path, original_filename = resolved
        try:
            with open(fetched_temp_path, 'rb') as f:
                file_content = f.read()
        except OSError as e:
            logger.error("Could not read fetched subtitle: %s", e)
            return jsonify({'error': 'Could not read fetched subtitle'}), 500
    else:
        if 'srtFile' not in request.files:
            return jsonify({'error': 'No subtitle file or OpenSubtitles selection provided'}), 400
        srt_file = request.files['srtFile']
        if srt_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        original_filename = srt_file.filename
        file_content = srt_file.read()

    allowed_exts = ('.srt', '.ass', '.ssa', '.sub')
    if not original_filename.lower().endswith(allowed_exts):
        return jsonify({'error': 'File must be a subtitle file (SRT, ASS, SSA, SUB)'}), 400
    # Decode file content
    try:
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
            async def srt_progress_async(entries, source_lang, translate_dest):
                translated_entries = []
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
                        translated_batch = await translation_service.translate_texts(
                            batch, source_lang, translate_dest, translator
                        )
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
                return translated_entries

            def srt_progress(entries, source_lang, translate_dest):
                return asyncio.run(srt_progress_async(entries, source_lang, translate_dest))

            translated_entries = srt_progress([
                SRTEntry(e['sequence_number'], e['start_time'], e['end_time'], e['text_lines']) for e in parsed
            ], source_lang, google_dest)
            if use_pinyin and dual_language:
                output_entries = []
                for orig_dict, trans_entry in zip(parsed, translated_entries):
                    en = _join_srt_text_lines(orig_dict['text_lines'])
                    zh = _join_srt_text_lines(trans_entry.text_lines)
                    pin = ' '.join(
                        line_to_pinyin(cl) for cl in trans_entry.text_lines if cl.strip()
                    )
                    combined_lines = [
                        _ass_english_line(en),
                        _ass_chinese_line(zh),
                        _ass_pinyin_line(pin),
                    ]
                    output_entries.append({
                        'sequence_number': trans_entry.sequence_number,
                        'start_time': trans_entry.start_time,
                        'end_time': trans_entry.end_time,
                        'text_lines': combined_lines
                    })
                translated_content = SubtitleParser.srt_output_entries_to_minimal_ass(output_entries)
            elif use_pinyin and not dual_language:
                output_entries = []
                for trans_entry in translated_entries:
                    zh = _join_srt_text_lines(trans_entry.text_lines)
                    pin = ' '.join(
                        line_to_pinyin(cl) for cl in trans_entry.text_lines if cl.strip()
                    )
                    output_entries.append({
                        'sequence_number': trans_entry.sequence_number,
                        'start_time': trans_entry.start_time,
                        'end_time': trans_entry.end_time,
                        'text_lines': [_ass_chinese_line(zh), _ass_pinyin_line(pin)],
                    })
                translated_content = SubtitleParser.srt_output_entries_to_minimal_ass(output_entries)
            elif dual_language:
                output_entries = []
                for orig_dict, trans_entry in zip(parsed, translated_entries):
                    combined_lines = [
                        _join_srt_text_lines(orig_dict['text_lines']),
                        _join_srt_text_lines(trans_entry.text_lines),
                    ]
                    output_entries.append({
                        'sequence_number': trans_entry.sequence_number,
                        'start_time': trans_entry.start_time,
                        'end_time': trans_entry.end_time,
                        'text_lines': combined_lines
                    })
                translated_content = SubtitleParser.to_srt(output_entries)
            else:
                translated_content = SubtitleParser.to_srt([
                    {
                        'sequence_number': e.sequence_number,
                        'start_time': e.start_time,
                        'end_time': e.end_time,
                        'text_lines': [_join_srt_text_lines(e.text_lines)] if e.text_lines else [''],
                    }
                    for e in translated_entries
                ])
            if use_pinyin:
                translated_filename = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.ass"
            else:
                translated_filename = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.srt"
        elif fmt == 'ass':
            texts = [d['text'] for d in parsed['dialogues']]
            total_lines = len(texts)
            translated_texts = []
            async def do_translate_ass_async():
                async with Translator() as translator:
                    batch_size = 100
                    for i in range(0, total_lines, batch_size):
                        batch = texts[i:i+batch_size]
                        translated_batch = await translation_service.translate_texts(
                            batch, source_lang, google_dest, translator
                        )
                        translated_texts.extend(translated_batch)
                        update_progress(min(i+batch_size, total_lines), total_lines)

            asyncio.run(do_translate_ass_async())
            if use_pinyin and dual_language:
                combined_texts = [
                    f"{_ass_english_line(_collapse_ass_dialogue(orig))}\\N"
                    f"{_ass_chinese_line(_collapse_ass_dialogue(tran))}\\N"
                    f"{_ass_pinyin_line(line_to_pinyin(_collapse_ass_dialogue(tran)))}"
                    for orig, tran in zip(texts, translated_texts)
                ]
                translated_content = SubtitleParser.to_ass(parsed, combined_texts)
            elif use_pinyin and not dual_language:
                combined_texts = [
                    f"{_ass_chinese_line(_collapse_ass_dialogue(tran))}\\N"
                    f"{_ass_pinyin_line(line_to_pinyin(_collapse_ass_dialogue(tran)))}"
                    for tran in translated_texts
                ]
                translated_content = SubtitleParser.to_ass(parsed, combined_texts)
            elif dual_language:
                combined_texts = [
                    f"{_ass_english_line(_collapse_ass_dialogue(orig))}\\N"
                    f"{_ass_chinese_line(_collapse_ass_dialogue(tran))}"
                    for orig, tran in zip(texts, translated_texts)
                ]
                translated_content = SubtitleParser.to_ass(parsed, combined_texts)
            else:
                combined_texts = [_ass_chinese_line(_collapse_ass_dialogue(t)) for t in translated_texts]
                translated_content = SubtitleParser.to_ass(parsed, combined_texts)
            translated_filename = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.ass"
        elif fmt == 'sub':
            texts = [d['text'] for d in parsed['subs']]
            total_lines = len(texts)
            translated_texts = []
            async def do_translate_sub_async():
                async with Translator() as translator:
                    batch_size = 100
                    for i in range(0, total_lines, batch_size):
                        batch = texts[i:i+batch_size]
                        translated_batch = await translation_service.translate_texts(
                            batch, source_lang, google_dest, translator
                        )
                        translated_texts.extend(translated_batch)
                        update_progress(min(i+batch_size, total_lines), total_lines)

            asyncio.run(do_translate_sub_async())
            if use_pinyin and dual_language:
                combined_texts = [
                    f"{_collapse_sub_text(orig)}|{_collapse_sub_text(tran)}|"
                    f"{line_to_pinyin(_collapse_sub_text(tran))}"
                    for orig, tran in zip(texts, translated_texts)
                ]
                translated_content = SubtitleParser.to_sub(parsed, combined_texts)
            elif use_pinyin and not dual_language:
                combined_texts = [
                    f"{_collapse_sub_text(tran)}|{line_to_pinyin(_collapse_sub_text(tran))}"
                    for tran in translated_texts
                ]
                translated_content = SubtitleParser.to_sub(parsed, combined_texts)
            elif dual_language:
                combined_texts = [
                    f"{_collapse_sub_text(orig)}|{_collapse_sub_text(tran)}"
                    for orig, tran in zip(texts, translated_texts)
                ]
                translated_content = SubtitleParser.to_sub(parsed, combined_texts)
            else:
                combined_texts = [_collapse_sub_text(t) for t in translated_texts]
                translated_content = SubtitleParser.to_sub(parsed, combined_texts)
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
        if fetched_temp_path and os.path.exists(fetched_temp_path):
            try:
                os.remove(fetched_temp_path)
                logger.info("Removed fetched subtitle temp file after translate")
            except OSError as e:
                logger.warning("Could not remove fetched temp file: %s", e)

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

@api_bp.route('/download/<file_id>', methods=['GET'])
def download_file(file_id):
    """
    Endpoint for downloading translated SRT files.
    
    Args:
        file_id: Unique identifier for the translated file
        
    Returns:
        File download response or error message
    """
    logger.info("test")
    try:
        # Validate file_id format (should be a UUID)
        if not re.match(r'^[a-f0-9-]{36}$', file_id):
            return jsonify({'error': 'Invalid file ID'}), 400
        
        # Find the file in temp directory
        temp_dir = tempfile.gettempdir()
        matching_files = [f for f in os.listdir(temp_dir) if f.startswith(file_id)]
        logger.info(f"file_id: {file_id}, temp_dir: {temp_dir}, matching_files: {matching_files}")
        print(f"file_id: {file_id}, temp_dir: {temp_dir}, matching_files: {matching_files}")
        
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

@api_bp.route('/translate/progress/<task_id>')
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


from srt_translator.api.opensubtitles_routes import register_opensubtitles_routes

register_opensubtitles_routes(api_bp)