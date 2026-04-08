"""Per-format translation: produce serialized subtitle text and output filename."""

from __future__ import annotations

import asyncio

from googletrans import Translator

from srt_translator.services.ass_markup import (
    html_styling_tags_to_ass,
    plain_text_for_translation_ass,
)
from srt_translator.services.pinyin_helper import line_to_pinyin
from srt_translator.services.srt_entry import SRTEntry
from srt_translator.services.subtitle_parser import SubtitleParser
from srt_translator.services.translation import translation_service
from srt_translator.subtitle_translate.ass_lines import (
    ass_chinese_line,
    ass_english_line,
    ass_pinyin_line,
    collapse_ass_dialogue,
    collapse_sub_text,
    join_srt_text_lines,
)
from srt_translator.subtitle_translate.batch import translate_line_batches


def run_srt_translate(
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
                    SRTEntry(
                        entry.sequence_number, entry.start_time, entry.end_time, lines
                    )
                )
                idx += line_count
                update_progress(idx, len(all_lines))
        return translated_entries

    entries = [
        SRTEntry(e["sequence_number"], e["start_time"], e["end_time"], e["text_lines"])
        for e in parsed
    ]
    translated_entries = asyncio.run(
        srt_progress_async(entries, source_lang, translate_dest)
    )

    if use_pinyin and dual_language:
        output_entries = []
        for orig_dict, trans_entry in zip(parsed, translated_entries):
            en = join_srt_text_lines(orig_dict["text_lines"])
            zh = join_srt_text_lines(trans_entry.text_lines)
            pin = " ".join(
                line_to_pinyin(cl) for cl in trans_entry.text_lines if cl.strip()
            )
            combined_lines = [
                ass_english_line(en),
                ass_chinese_line(zh),
                ass_pinyin_line(pin),
            ]
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
            zh = join_srt_text_lines(trans_entry.text_lines)
            pin = " ".join(
                line_to_pinyin(cl) for cl in trans_entry.text_lines if cl.strip()
            )
            output_entries.append(
                {
                    "sequence_number": trans_entry.sequence_number,
                    "start_time": trans_entry.start_time,
                    "end_time": trans_entry.end_time,
                    "text_lines": [ass_chinese_line(zh), ass_pinyin_line(pin)],
                }
            )
        content = SubtitleParser.srt_output_entries_to_minimal_ass(output_entries)
    elif dual_language:
        output_entries = []
        for orig_dict, trans_entry in zip(parsed, translated_entries):
            combined_lines = [
                join_srt_text_lines(orig_dict["text_lines"]),
                join_srt_text_lines(trans_entry.text_lines),
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
                    "text_lines": [join_srt_text_lines(e.text_lines)]
                    if e.text_lines
                    else [""],
                }
                for e in translated_entries
            ]
        )

    ext = "ass" if use_pinyin else "srt"
    fname = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.{ext}"
    return content, fname


def run_ass_translate(
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
        translate_line_batches(texts_plain, source_lang, google_dest, update_progress)
    )

    if use_pinyin and dual_language:
        combined_texts = [
            f"{ass_english_line(collapse_ass_dialogue(html_styling_tags_to_ass(orig)))}\\N"
            f"{ass_chinese_line(collapse_ass_dialogue(tran))}\\N"
            f"{ass_pinyin_line(line_to_pinyin(collapse_ass_dialogue(tran)))}"
            for orig, tran in zip(texts_raw, translated_texts)
        ]
    elif use_pinyin and not dual_language:
        combined_texts = [
            f"{ass_chinese_line(collapse_ass_dialogue(tran))}\\N"
            f"{ass_pinyin_line(line_to_pinyin(collapse_ass_dialogue(tran)))}"
            for tran in translated_texts
        ]
    elif dual_language:
        combined_texts = [
            f"{ass_english_line(collapse_ass_dialogue(html_styling_tags_to_ass(orig)))}\\N"
            f"{ass_chinese_line(collapse_ass_dialogue(tran))}"
            for orig, tran in zip(texts_raw, translated_texts)
        ]
    else:
        combined_texts = [
            ass_chinese_line(collapse_ass_dialogue(t)) for t in translated_texts
        ]

    content = SubtitleParser.to_ass(parsed, combined_texts)
    fname = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.ass"
    return content, fname


def run_sub_translate(
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
        translate_line_batches(texts, source_lang, google_dest, update_progress)
    )

    if use_pinyin and dual_language:
        combined_texts = [
            f"{collapse_sub_text(orig)}|{collapse_sub_text(tran)}|"
            f"{line_to_pinyin(collapse_sub_text(tran))}"
            for orig, tran in zip(texts, translated_texts)
        ]
    elif use_pinyin and not dual_language:
        combined_texts = [
            f"{collapse_sub_text(tran)}|{line_to_pinyin(collapse_sub_text(tran))}"
            for tran in translated_texts
        ]
    elif dual_language:
        combined_texts = [
            f"{collapse_sub_text(orig)}|{collapse_sub_text(tran)}"
            for orig, tran in zip(texts, translated_texts)
        ]
    else:
        combined_texts = [collapse_sub_text(t) for t in translated_texts]

    content = SubtitleParser.to_sub(parsed, combined_texts)
    fname = f"{base_name}_{target_lang}{'_dual' if dual_language else ''}.sub"
    return content, fname


FORMAT_RUNNERS = {
    "srt": run_srt_translate,
    "ass": run_ass_translate,
    "sub": run_sub_translate,
}
