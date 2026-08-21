import logging
import re
from typing import Generator, Optional

import ollama

from metrics.store import MetricsStore


class OllamaClient:
    # Remove apenas um bloco de raciocínio inicial delimitado por
    # " thinking" ... " response". Âncorado ao início da resposta para não
    # corromper conteúdo legítimo que contenha "response" no meio.
    THINK_PATTERN = re.compile(r"^\s*thinking\b.*?response\b", re.DOTALL)

    def __init__(
        self,
        model: str = "gemma3:4b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        request_timeout: int = 300,
        logger: Optional[logging.Logger] = None,
        strip_thinking: bool = True,
        think: bool = False,
        metrics: Optional[MetricsStore] = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.logger = logger
        self.strip_thinking = strip_thinking
        self.think = think
        self._metrics = metrics or MetricsStore(logger=logger)
        self._client = ollama.Client(host=self.base_url, timeout=request_timeout)

    @staticmethod
    def _strip_thinking(text: str) -> str:
        return OllamaClient.THINK_PATTERN.sub("", text).strip()

    def supports_thinking(self) -> bool:
        """Modelos de raciocínio (qwen3/qwq) suportam o modo `think`."""
        name = self.model.lower()
        return "qwen3" in name or "qwq" in name

    def _record(self, response: dict, kind: str, success: bool = True, error: Optional[str] = None) -> None:
        """Registra métricas de uma chamada ao Ollama a partir da resposta."""
        try:
            self._metrics.record_llm_call(
                model=self.model,
                kind=kind,
                prompt_tokens=response.get("prompt_eval_count", 0),
                completion_tokens=response.get("eval_count", 0),
                total_duration_ms=(response.get("total_duration") or 0) / 1_000_000,
                eval_duration_ms=(response.get("eval_duration") or 0) / 1_000_000,
                success=success,
                error=error,
            )
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Metrics record failed: {e}")

    def ask(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        strip_thinking: Optional[bool] = None,
        think: Optional[bool] = None,
    ) -> str:
        _think = think if think is not None else self.think
        try:
            response = self._client.generate(
                model=self.model,
                prompt=prompt,
                think=_think,
                options={
                    "temperature": temperature if temperature is not None else self.temperature,
                    "num_predict": max_tokens if max_tokens is not None else self.max_tokens,
                },
            )
        except Exception as e:
            if _think:
                try:
                    response = self._client.generate(
                        model=self.model,
                        prompt=prompt,
                        think=False,
                        options={
                            "temperature": temperature if temperature is not None else self.temperature,
                            "num_predict": max_tokens if max_tokens is not None else self.max_tokens,
                        },
                    )
                except Exception as e2:
                    self._record({}, "generate", success=False, error=str(e2))
                    raise
            else:
                self._record({}, "generate", success=False, error=str(e))
                raise
        self._record(response, "generate")
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
        think: Optional[bool] = None,
    ) -> Generator[str, None, None]:
        _strip = strip_thinking if strip_thinking is not None else self.strip_thinking
        _think = think if think is not None else self.think
        stream = self._client.generate(
            model=self.model,
            prompt=prompt,
            think=_think,
            options={
                "temperature": temperature if temperature is not None else self.temperature,
                "num_predict": max_tokens if max_tokens is not None else self.max_tokens,
            },
            stream=True,
        )
        buffer = ""
        in_think = False
        last_stats: dict = {}
        try:
            for part in stream:
                if part.get("done"):
                    last_stats = dict(part)
                    continue
                content = part.get("response", "")
                if not content:
                    continue
                if not _strip:
                    yield content
                    continue
                buffer += content
                while buffer:
                    if not in_think:
                        idx = buffer.find(" thinking")
                        if idx == -1:
                            yield buffer
                            buffer = ""
                        elif idx == 0:
                            buffer = buffer[len(" thinking"):]
                            in_think = True
                        else:
                            yield buffer
                            buffer = ""
                    else:
                        idx = buffer.find(" response")
                        if idx == -1:
                            buffer = ""
                        else:
                            buffer = buffer[idx + len(" response"):]
                            in_think = False
                            if buffer:
                                yield buffer
                                buffer = ""
        except Exception as e:
            self._record({}, "stream", success=False, error=str(e))
            raise
        finally:
            self._record(last_stats, "stream")

    def list_models(self) -> list:
        try:
            models = self._client.list()
            return [m.model for m in models.models]
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to list models: {e}")
            return [self.model]
