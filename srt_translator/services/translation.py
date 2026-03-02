"""Translation service for handling SRT file translations."""
from typing import List, Tuple
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

translation_service = TranslationService()
