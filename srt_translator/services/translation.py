"""Translation service for handling SRT file translations."""
from typing import List
import pysrt
from googletrans import Translator
import re
import logging
from .srt_entry import SRTEntry

# Configure logging for debugging and monitoring
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PINYIN_TARGET_LANGS = frozenset({'zh-cn-pinyin', 'zh-tw-pinyin'})


def google_translate_dest(target_lang: str) -> str:
    """Map UI/API target codes to a language code accepted by Google Translate."""
    if target_lang == 'zh-cn-pinyin':
        return 'zh-cn'
    if target_lang == 'zh-tw-pinyin':
        return 'zh-tw'
    return target_lang


def is_pinyin_target(target_lang: str) -> bool:
    return target_lang in PINYIN_TARGET_LANGS


class TranslationService:
    """
    Handles text translation using googletrans 4.x (async ``Translator.translate``; call from sync code via ``asyncio.run`` in the API).
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
            'zh-cn-pinyin': 'Chinese (Simplified) + Pinyin',
            'zh-tw-pinyin': 'Chinese (Traditional) + Pinyin',
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


    async def translate_texts(
        self, texts: list, source_lang: str, target_lang: str, translator: Translator
    ) -> list:
        cleaned_texts = [self._preprocess_subtitle_text(t) if t.strip() else t for t in texts]
        is_empty = [not t.strip() for t in texts]
        to_translate = [t for t in cleaned_texts if t.strip()]
        if not to_translate:
            return texts
        results = await translator.translate(to_translate, dest=target_lang, src=source_lang)
        if isinstance(results, list):
            translated = [
                self._postprocess_subtitle_text(r.text) if hasattr(r, 'text') else '' for r in results
            ]
        else:
            translated = [self._postprocess_subtitle_text(results.text)]
        output = []
        idx = 0
        for empty, orig in zip(is_empty, texts):
            if empty:
                output.append(orig)
            else:
                output.append(translated[idx])
                idx += 1
        return output

    async def translate_subtitle_entries_async(
        self, entries: List[SRTEntry], source_lang: str, target_lang: str
    ) -> List[SRTEntry]:
        translated_entries = []
        total_entries = len(entries)
        logger.info(f"Starting batch translation of {total_entries} entries from {source_lang} to {target_lang}")
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
                translated_batch = await self.translate_texts(batch, source_lang, target_lang, translator)
                translated_lines.extend(translated_batch)
            idx = 0
            for entry, line_count in zip(entries, entry_line_counts):
                lines = translated_lines[idx : idx + line_count]
                translated_entry = SRTEntry(
                    entry.sequence_number,
                    entry.start_time,
                    entry.end_time,
                    lines,
                )
                translated_entries.append(translated_entry)
                idx += line_count
                if (entry.sequence_number % 10 == 0) or (entry == entries[-1]):
                    logger.info(f"Translated entry {entry.sequence_number}/{total_entries}")
        logger.info("Batch translation completed successfully")
        return translated_entries

    def _preprocess_subtitle_text(self, text: str) -> str:
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _postprocess_subtitle_text(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        return text

translation_service = TranslationService()
