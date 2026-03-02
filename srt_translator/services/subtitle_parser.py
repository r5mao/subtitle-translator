import re

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

subtitle_parser = SubtitleParser()