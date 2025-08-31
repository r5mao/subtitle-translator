"""Translation service for handling SRT file translations."""
from typing import List, Tuple
import pysrt
from googletrans import Translator

class TranslationService:
    """Service for handling SRT file translations."""
    
    def __init__(self):
        self.translator = Translator()
    
    def translate_srt(self, srt_content: str, target_lang: str = 'en') -> Tuple[str, List[dict]]:
        """
        Translate SRT content to the target language.
        
        Args:
            srt_content: Raw SRT file content as string
            target_lang: Target language code (e.g., 'es', 'fr', 'de')
            
        Returns:
            Tuple of (translated_srt, translations) where translations is a list of
            translation results for tracking/analysis
        """
        try:
            subs = pysrt.from_string(srt_content)
            translations = []
            
            for sub in subs:
                if not sub.text.strip():
                    continue
                    
                translation = self.translator.translate(
                    sub.text,
                    dest=target_lang
                )
                
                translations.append({
                    'original': sub.text,
                    'translated': translation.text,
                    'src_lang': translation.src,
                    'dest_lang': translation.dest
                })
                
                sub.text = translation.text
            
            return '\n'.join(map(str, subs)), translations
            
        except Exception as e:
            raise ValueError(f"Translation failed: {str(e)}") from e

# Singleton instance
translation_service = TranslationService()
