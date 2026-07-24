import logging
import re
from typing import Generator, Optional

import ollama


class OllamaClient:
    THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)

    def __init__(
        self,
        model: str = "qwen3:8b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        request_timeout: int = 120,
        logger: Optional[logging.Logger] = None,
        strip_thinking: bool = True,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.logger = logger
        self.strip_thinking = strip_thinking
        self._client = ollama.Client(host=self.base_url, timeout=request_timeout)

    @staticmethod
    def _strip_thinking(text: str) -> str:
        return OllamaClient.THINK_PATTERN.sub("", text).strip()

    def ask(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        strip_thinking: Optional[bool] = None,
    ) -> str:
        response = self._client.generate(
            model=self.model,
            prompt=prompt,
            options={
                "temperature": temperature if temperature is not None else self.temperature,
                "num_predict": max_tokens if max_tokens is not None else self.max_tokens,
            },
        )
        answer = response.get("response", "")
        if strip_thinking if strip_thinking is not None else self.strip_thinking:
            answer = self._strip_thinking(answer)
        return answer

    def ask_stream(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        strip_thinking: Optional[bool] = None,
    ) -> Generator[str, None, None]:
        _strip = strip_thinking if strip_thinking is not None else self.strip_thinking
        stream = self._client.generate(
            model=self.model,
            prompt=prompt,
            options={
                "temperature": temperature if temperature is not None else self.temperature,
                "num_predict": max_tokens if max_tokens is not None else self.max_tokens,
            },
            stream=True,
        )
        buffer = ""
        in_think = False
        for part in stream:
            content = part.get("response", "")
            if not content:
                continue
            if not _strip:
                yield content
                continue
            buffer += content
            while buffer:
                if not in_think:
                    idx = buffer.find("<think>")
                    if idx == -1:
                        yield buffer
                        buffer = ""
                    else:
                        if idx > 0:
                            yield buffer[:idx]
                        buffer = buffer[idx + 7:]
                        in_think = True
                else:
                    idx = buffer.find("</think>")
                    if idx == -1:
                        buffer = ""
                    else:
                        buffer = buffer[idx + 8:]
                        in_think = False

    def list_models(self) -> list:
        try:
            models = self._client.list()
            return [m.model for m in models.models]
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to list models: {e}")
            return [self.model]
