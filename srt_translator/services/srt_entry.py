from typing import List


class SRTEntry:
    """
    Represents a single subtitle entry in an SRT file.

    Each SRT entry contains:
    - sequence_number: The numerical order of the subtitle
    - start_time: When the subtitle should appear (HH:MM:SS,mmm format)
    - end_time: When the subtitle should disappear
    - text_lines: List of text lines for this subtitle entry
    """

    def __init__(
        self,
        sequence_number: int,
        start_time: str,
        end_time: str,
        text_lines: List[str],
    ):
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
        text_content = "\n".join(self.text_lines)
        return f"{self.sequence_number}\n{self.start_time} --> {self.end_time}\n{text_content}\n"


srt_entry = SRTEntry(
    1, "00:00:01,000", "00:00:04,000", ["Hello, world!", "This is a subtitle entry."]
)
