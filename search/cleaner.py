import logging
import re
from typing import Optional


class ContentCleaner:
    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger

    def clean(self, text: str) -> str:
        if not text:
            return ""

        text = re.sub(r"\r\n", "\n", text)
        text = re.sub(r"\r", "\n", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"&#39;", "'", text)

        text = text.strip()

        if self.logger:
            self.logger.debug(f"Cleaned text: {len(text)} chars")
        return text
