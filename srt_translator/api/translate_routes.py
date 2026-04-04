"""Translate and download routes (SRT/ASS/SUB)."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file, Response, stream_with_context
from googletrans import Translator

from srt_translator.services.ass_markup import (
    ass_escape_plain_text,
    escape_ass_plain_runs,
    html_styling_tags_to_ass,
    plain_text_for_translation_ass,
)
from srt_translator.services.fetched_subtitle_file import (
    is_valid_fetched_id,
    resolve_fetched_subtitle_file,
)
from srt_translator.services.pinyin_helper import line_to_pinyin
from srt_translator.services.srt_entry import SRTEntry
from srt_translator.services.subtitle_parser import SubtitleParser
from srt_translator.services.translation import (
    google_translate_dest,
    is_pinyin_target,
    translation_service,
)

logger = logging.getLogger(__name__)


def _ass_english_line(text: str) -> str:
    return f"{{\\fs10}}{escape_ass_plain_runs(text)}{{\\r}}"


def _ass_chinese_line(text: str) -> str:
    return f"{{\\fs12}}{escape_ass_plain_runs(text)}{{\\r}}"


def _ass_pinyin_line(pinyin_plain: str) -> str:
    return f"{{\\fs8}}{ass_escape_plain_text(pinyin_plain)}{{\\r}}"


def _join_srt_text_lines(lines: list) -> str:
    return " ".join(x.strip() for x in (lines or []) if x.strip())


def _collapse_ass_dialogue(text: str) -> str:
    if not text:
        return ""
    return " ".join(p.strip() for p in text.split(r"\N") if p.strip())


def _collapse_sub_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(p.strip() for p in re.split(r"[\r\n]+", text) if p.strip())


def _format_translation_duration(total_ms: int) -> str:
    duration_minutes = total_ms // 60000
    duration_seconds = (total_ms % 60000) // 1000
    duration_ms = total_ms % 1000
    if duration_minutes:
        return f"{duration_minutes} mins {duration_seconds} seconds {duration_ms} ms"
    if duration_seconds:
        return f"{duration_seconds} seconds {duration_ms} ms"
    return f"{duration_ms} ms"


async def _translate_line_batches(
    lines: list[str],
    source_lang: str,
    translate_dest: str,
    update_progress,
) -> list[str]:
    out: list[str] = []
    async with Translator() as translator:
        batch_size = 100
        total = len(lines)
        for i in range(0, total, batch_size):
            batch = lines[i : i + batch_size]
            translated_batch = await translation_service.translate_texts(
                batch, source_lang, translate_dest, translator
            )
            out.extend(translated_batch)
            update_progress(min(i + batch_size, total), total)
    return out


def _run_srt_translate(
    parsed: list,
    source_lang: str,
    translate_dest: str,
    use_pinyin: bool,
    dual_language: bool,
    base_name: str,
    target_lang: str,
    update_progress,
) -> tuple[str, str]:
    async def srt_progress_async(entries, src, dest):
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
                batch = all_lines[i : i + batch_size]
                translated_batch = await translation_service.translate_texts(
                    batch, src, dest, translator
                )
                translated_lines.extend(translated_batch)
                update_progress(min(i + batch_size, len(all_lines)), len(all_lines))
            idx = 0
            for entry, line_count in zip(entries, entry_line_counts):
                lines = translated_lines[idx : idx + line_count]
                translated_entries.append(
                    SRTEntry(entry.sequence_number, entry.start_time, entry.end_time, lines)
                )
                idx += line_count
                update_progress(idx, len(all_lines))
        return translated_entries

    entries = [
        SRTEntry(e["sequence_number"], e["start_time"], e["end_time"], e["text_lines"]) for e in parsed
    ]
    translated_entries = asyncio.run(srt_progress_async(entries, source_lang, translate_dest))

    if use_pinyin and dual_language:
        output_entries = []
        for orig_dict, trans_entry in zip(parsed, translated_entries):
            en = _join_srt_text_lines(orig_dict["text_lines"])
            zh = _join_srt_text_lines(trans_entry.text_lines)
            pin = " ".join(line_to_pinyin(cl) for cl in trans_entry.text_lines if cl.strip())
            combined_lines = [_ass_english_line(en), _ass_chinese_line(zh), _ass_pinyin_line(pin)]
            output_entries.append(
                {
                    "sequence_number": trans_entry.sequence_number,
                    "start_time": trans_entry.start_time,
                    "end_time": trans_entry.end_time,
                    "text_lines": combined_lines,
                }
            )
        content = SubtitleParser.srt_output_entries_to_minimal_ass(output_entries)
    elif use_pinyin and not dual_language:
        output_entries = []
        for trans_entry in translated_entries:
            zh = _join_srt_text_lines(trans_entry.text_lines)
            pin = " ".join(line_to_pinyin(cl) for cl in trans_entry.text_lines if cl.strip())
            output_entries.append(
                {
                    "sequence_number": trans_entry.sequence_number,
                    "start_time": trans_entry.start_time,
                    "end_time": trans_entry.end_time,
                    "text_lines": [_ass_chinese_line(zh), _ass_pinyin_line(pin)],
                }
            )
        content = SubtitleParser.srt_output_entries_to_minimal_ass(output_entries)
    elif dual_language:
        output_entries = []
        for orig_dict, trans_entry in zip(parsed, translated_entries):
            combined_lines = [
                _join_srt_text_lines(orig_dict["text_lines"]),
                _join_srt_text_lines(trans_entry.text_lines),
            ]
            output_entries.append(
                {
                    "sequence_number": trans_entry.sequence_number,
                    "start_time": trans_entry.start_time,
                    "end_time": trans_entry.end_time,
                    "text_lines": combined_lines,
                }
            )
        content = SubtitleParser.to_srt(output_entries)
    else:
        content = SubtitleParser.to_srt(
            [
                {
                    "sequence_number": e.sequence_number,
                    "start_time": e.start_time,
                    "end_time": e.end_time,
                    "text_lines": [_join_srt_text_lines(e.text_lines)] if e.text_lines else [""],
                }
                for e in translated_entries
            ]
        )

    ext = "ass" if use_pinyin else "srt"
    fname = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.{ext}"
    return content, fname


def _run_ass_translate(
    parsed: dict,
    source_lang: str,
    google_dest: str,
    use_pinyin: bool,
    dual_language: bool,
    base_name: str,
    target_lang: str,
    update_progress,
) -> tuple[str, str]:
    texts_raw = [d["text"] for d in parsed["dialogues"]]
    texts_plain = [plain_text_for_translation_ass(t) for t in texts_raw]
    translated_texts = asyncio.run(
        _translate_line_batches(texts_plain, source_lang, google_dest, update_progress)
    )

    if use_pinyin and dual_language:
        combined_texts = [
            f"{_ass_english_line(_collapse_ass_dialogue(html_styling_tags_to_ass(orig)))}\\N"
            f"{_ass_chinese_line(_collapse_ass_dialogue(tran))}\\N"
            f"{_ass_pinyin_line(line_to_pinyin(_collapse_ass_dialogue(tran)))}"
            for orig, tran in zip(texts_raw, translated_texts)
        ]
    elif use_pinyin and not dual_language:
        combined_texts = [
            f"{_ass_chinese_line(_collapse_ass_dialogue(tran))}\\N"
            f"{_ass_pinyin_line(line_to_pinyin(_collapse_ass_dialogue(tran)))}"
            for tran in translated_texts
        ]
    elif dual_language:
        combined_texts = [
            f"{_ass_english_line(_collapse_ass_dialogue(html_styling_tags_to_ass(orig)))}\\N"
            f"{_ass_chinese_line(_collapse_ass_dialogue(tran))}"
            for orig, tran in zip(texts_raw, translated_texts)
        ]
    else:
        combined_texts = [_ass_chinese_line(_collapse_ass_dialogue(t)) for t in translated_texts]

    content = SubtitleParser.to_ass(parsed, combined_texts)
    fname = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.ass"
    return content, fname


def _run_sub_translate(
    parsed: dict,
    source_lang: str,
    google_dest: str,
    use_pinyin: bool,
    dual_language: bool,
    base_name: str,
    target_lang: str,
    update_progress,
) -> tuple[str, str]:
    texts = [d["text"] for d in parsed["subs"]]
    translated_texts = asyncio.run(
        _translate_line_batches(texts, source_lang, google_dest, update_progress)
    )

    if use_pinyin and dual_language:
        combined_texts = [
            f"{_collapse_sub_text(orig)}|{_collapse_sub_text(tran)}|"
            f"{line_to_pinyin(_collapse_sub_text(tran))}"
            for orig, tran in zip(texts, translated_texts)
        ]
    elif use_pinyin and not dual_language:
        combined_texts = [
            f"{_collapse_sub_text(tran)}|{line_to_pinyin(_collapse_sub_text(tran))}"
            for tran in translated_texts
        ]
    elif dual_language:
        combined_texts = [
            f"{_collapse_sub_text(orig)}|{_collapse_sub_text(tran)}"
            for orig, tran in zip(texts, translated_texts)
        ]
    else:
        combined_texts = [_collapse_sub_text(t) for t in translated_texts]

    content = SubtitleParser.to_sub(parsed, combined_texts)
    fname = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.sub"
    return content, fname


def register_translate_routes(api_bp: Blueprint, translation_progress: dict) -> None:
    """Register /translate, /download/<id>, and SSE progress on ``api_bp``."""

    @api_bp.route("/translate", methods=["POST"])
    def translate_srt():
        if "sourceLanguage" not in request.form or "targetLanguage" not in request.form:
            return jsonify({"error": "Source and target languages required"}), 400
        source_lang = request.form["sourceLanguage"]
        target_lang = request.form["targetLanguage"]
        if source_lang == target_lang:
            return jsonify({"error": "Source and target languages cannot be the same"}), 400
        if source_lang not in translation_service.language_names:
            return jsonify({"error": f"Unsupported source language: {source_lang}"}), 400
        if target_lang not in translation_service.language_names:
            return jsonify({"error": f"Unsupported target language: {target_lang}"}), 400
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
                    {"error": "Fetched subtitle expired or not found. Search and select again."}
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
                return jsonify({"error": "No subtitle file or OpenSubtitles selection provided"}), 400
            srt_file = request.files["srtFile"]
            if srt_file.filename == "":
                return jsonify({"error": "No file selected"}), 400
            original_filename = srt_file.filename
            file_content = srt_file.read()

        allowed_exts = (".srt", ".ass", ".ssa", ".sub")
        if not original_filename.lower().endswith(allowed_exts):
            return jsonify({"error": "File must be a subtitle file (SRT, ASS, SSA, SUB)"}), 400

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
                    {"error": "Unable to decode file. Please ensure it's a valid text file."}
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
            return jsonify({"error": f"Invalid subtitle format: {str(e)}"}), 400

        def update_progress(current, total):
            translation_progress[task_id]["progress"] = int((current / total) * 100)

        try:
            translation_timer_start = datetime.now()
            if fmt == "srt":
                translated_content, translated_filename = _run_srt_translate(
                    parsed,
                    source_lang,
                    google_dest,
                    use_pinyin,
                    dual_language,
                    base_name,
                    target_lang,
                    update_progress,
                )
            elif fmt == "ass":
                translated_content, translated_filename = _run_ass_translate(
                    parsed,
                    source_lang,
                    google_dest,
                    use_pinyin,
                    dual_language,
                    base_name,
                    target_lang,
                    update_progress,
                )
            elif fmt == "sub":
                translated_content, translated_filename = _run_sub_translate(
                    parsed,
                    source_lang,
                    google_dest,
                    use_pinyin,
                    dual_language,
                    base_name,
                    target_lang,
                    update_progress,
                )
            else:
                raise ValueError("Unsupported subtitle format")

            translation_progress[task_id]["progress"] = 100
            logger.info("Translation completed for %s format", fmt)

            total_ms = int((datetime.now() - translation_timer_start).total_seconds() * 1000)
            duration_str = _format_translation_duration(total_ms)
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
                    "sourceLanguage": translation_service.language_names.get(source_lang, source_lang),
                    "targetLanguage": translation_service.language_names.get(target_lang, target_lang),
                    "translationStartedAt": translation_start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "translationDuration": duration_str,
                }
            )
        except Exception as e:
            logger.error("Translation error: %s", e)
            return jsonify({"error": f"Translation failed: {str(e)}"}), 500

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
