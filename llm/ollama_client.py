import logging
from typing import Generator, Optional

import ollama


class OllamaClient:
    def __init__(
        self,
        model: str = "qwen3:8b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        request_timeout: int = 120,
        logger: Optional[logging.Logger] = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.logger = logger
        self._client = ollama.Client(host=self.base_url, timeout=request_timeout)

    def ask(self, prompt: str) -> str:
        response = self._client.generate(
            model=self.model,
            prompt=prompt,
            options={
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        )
        return response.get("response", "")

    def ask_stream(self, prompt: str) -> Generator[str, None, None]:
        stream = self._client.generate(
            model=self.model,
            prompt=prompt,
            options={
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
            stream=True,
        )
        for part in stream:
            content = part.get("response", "")
            if content:
                yield content

    def list_models(self) -> list:
        try:
            models = self._client.list()
            return [m.model for m in models.models]
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to list models: {e}")
            return [self.model]
