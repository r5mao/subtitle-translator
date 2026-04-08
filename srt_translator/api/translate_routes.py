"""Translate and download routes (SRT/ASS/SUB)."""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from srt_translator.services.fetched_subtitle_file import (
    is_valid_fetched_id,
    resolve_fetched_subtitle_file,
)
from srt_translator.services.subtitle_parser import SubtitleParser
from srt_translator.services.translation import (
    google_translate_dest,
    is_pinyin_target,
    translation_service,
)
from srt_translator.subtitle_translate.ass_lines import format_translation_duration
from srt_translator.subtitle_translate.jobs import FORMAT_RUNNERS

logger = logging.getLogger(__name__)


def register_translate_routes(api_bp: Blueprint, translation_progress: dict) -> None:
    """Register /translate, /download/<id>, and SSE progress on ``api_bp``."""

    @api_bp.route("/translate", methods=["POST"])
    def translate_srt():
        if "sourceLanguage" not in request.form or "targetLanguage" not in request.form:
            return jsonify({"error": "Source and target languages required"}), 400
        source_lang = request.form["sourceLanguage"]
        target_lang = request.form["targetLanguage"]
        if source_lang == target_lang:
            return jsonify(
                {"error": "Source and target languages cannot be the same"}
            ), 400
        if source_lang not in translation_service.language_names:
            return jsonify(
                {"error": f"Unsupported source language: {source_lang}"}
            ), 400
        if target_lang not in translation_service.language_names:
            return jsonify(
                {"error": f"Unsupported target language: {target_lang}"}
            ), 400
        google_dest = google_translate_dest(target_lang)
        use_pinyin = is_pinyin_target(target_lang)
        dual_language = request.form.get("dualLanguage", "false").strip().lower() in (
            "true",
            "on",
            "1",
            "yes",
        )
        task_id = request.form["taskId"]
        translation_progress[task_id] = {"progress": 0, "status": "started"}

        fetched_id = request.form.get("fetchedId", "").strip()
        file_content = None
        original_filename = None
        fetched_temp_path = None

        if fetched_id:
            if not is_valid_fetched_id(fetched_id):
                return jsonify({"error": "Invalid fetched subtitle id"}), 400
            resolved = resolve_fetched_subtitle_file(fetched_id)
            if not resolved:
                return jsonify(
                    {
                        "error": "Fetched subtitle expired or not found. Search and select again."
                    }
                ), 404
            fetched_temp_path, original_filename = resolved
            try:
                with open(fetched_temp_path, "rb") as f:
                    file_content = f.read()
            except OSError as e:
                logger.error("Could not read fetched subtitle: %s", e)
                return jsonify({"error": "Could not read fetched subtitle"}), 500
        else:
            if "srtFile" not in request.files:
                return jsonify(
                    {"error": "No subtitle file or OpenSubtitles selection provided"}
                ), 400
            srt_file = request.files["srtFile"]
            if srt_file.filename == "":
                return jsonify({"error": "No file selected"}), 400
            original_filename = srt_file.filename
            file_content = srt_file.read()

        allowed_exts = (".srt", ".ass", ".ssa", ".sub")
        if not original_filename.lower().endswith(allowed_exts):
            return jsonify(
                {"error": "File must be a subtitle file (SRT, ASS, SSA, SUB)"}
            ), 400

        try:
            encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
            content = None
            for encoding in encodings:
                try:
                    content = file_content.decode(encoding)
                    logger.info("Successfully decoded file using %s encoding", encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if content is None:
                return jsonify(
                    {
                        "error": "Unable to decode file. Please ensure it's a valid text file."
                    }
                ), 400
        except Exception as e:
            logger.error("Error reading file: %s", e)
            return jsonify({"error": "Error reading file content"}), 400

        translation_start_time = datetime.now()
        logger.info(
            "Translation started at %s",
            translation_start_time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        try:
            base_name = os.path.splitext(original_filename)[0]
            fmt, parsed = SubtitleParser.parse(content)
            logger.info("Parsed subtitle file as format: %s", fmt)
        except ValueError as e:
            logger.error("Subtitle parsing error: %s", e)
            return jsonify({"error": f"Invalid subtitle format: {e!s}"}), 400

        def update_progress(current, total):
            translation_progress[task_id]["progress"] = int((current / total) * 100)

        try:
            translation_timer_start = datetime.now()
            runner = FORMAT_RUNNERS.get(fmt)
            if not runner:
                raise ValueError("Unsupported subtitle format")
            translated_content, translated_filename = runner(
                parsed,
                source_lang,
                google_dest,
                use_pinyin,
                dual_language,
                base_name,
                target_lang,
                update_progress,
            )

            translation_progress[task_id]["progress"] = 100
            logger.info("Translation completed for %s format", fmt)

            total_ms = int(
                (datetime.now() - translation_timer_start).total_seconds() * 1000
            )
            duration_str = format_translation_duration(total_ms)
            logger.info("Translation took %s", duration_str)

            file_id = str(uuid.uuid4())
            temp_dir = tempfile.gettempdir()
            temp_file_path = os.path.join(temp_dir, f"{file_id}_{translated_filename}")
            with open(temp_file_path, "w", encoding="utf-8") as temp_file:
                temp_file.write(translated_content)
            logger.info("Created translated file: %s", temp_file_path)

            if fetched_temp_path and os.path.exists(fetched_temp_path):
                try:
                    os.remove(fetched_temp_path)
                    logger.info("Removed fetched subtitle temp file after translate")
                except OSError as e:
                    logger.warning("Could not remove fetched temp file: %s", e)

            return jsonify(
                {
                    "success": True,
                    "message": "Translation completed successfully",
                    "downloadUrl": f"/api/download/{file_id}",
                    "filename": translated_filename,
                    "sourceLanguage": translation_service.language_names.get(
                        source_lang, source_lang
                    ),
                    "targetLanguage": translation_service.language_names.get(
                        target_lang, target_lang
                    ),
                    "translationStartedAt": translation_start_time.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "translationDuration": duration_str,
                }
            )
        except Exception as e:
            logger.error("Translation error: %s", e)
            return jsonify({"error": f"Translation failed: {e!s}"}), 500

    @api_bp.route("/download/<file_id>", methods=["GET"])
    def download_file(file_id):
        try:
            if not re.match(r"^[a-f0-9-]{36}$", file_id):
                return jsonify({"error": "Invalid file ID"}), 400

            temp_dir = tempfile.gettempdir()
            matching_files = [f for f in os.listdir(temp_dir) if f.startswith(file_id)]
            logger.info(
                "download file_id=%s temp_dir=%s matches=%s",
                file_id,
                temp_dir,
                len(matching_files),
            )

            if not matching_files:
                return jsonify({"error": "File not found or expired"}), 404

            file_path = os.path.join(temp_dir, matching_files[0])
            if not os.path.exists(file_path):
                return jsonify({"error": "File not found"}), 404

            filename = matching_files[0].split("_", 1)[1]

            def cleanup_file():
                def delayed_cleanup():
                    time.sleep(300)
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logger.info("Cleaned up temporary file: %s", file_path)
                    except Exception as ex:
                        logger.error("Error cleaning up file %s: %s", file_path, ex)

                cleanup_thread = threading.Thread(target=delayed_cleanup)
                cleanup_thread.daemon = True
                cleanup_thread.start()

            cleanup_file()

            return send_file(
                file_path,
                as_attachment=True,
                download_name=filename,
                mimetype="text/plain",
            )
        except Exception as e:
            logger.error("Download error: %s", e)
            return jsonify({"error": "Error downloading file"}), 500

    @api_bp.route("/translate/progress/<task_id>")
    def sse_translation_progress(task_id):
        @stream_with_context
        def event_stream():
            last_progress = -1
            while True:
                progress = translation_progress.get(task_id, {}).get("progress", 0)
                if progress != last_progress:
                    yield f"data: {progress}\n\n"
                    last_progress = progress
                if progress >= 100:
                    break
                time.sleep(0.5)

        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",
        }
        return Response(event_stream(), headers=headers)
