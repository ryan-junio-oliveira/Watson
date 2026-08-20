"""Reconhecimento de fala (Speech-to-Text) local via faster-whisper.

Captura o audio do microfone com deteccao de atividade de voz (VAD simples por
RMS) e transcreve com Whisper. Tudo roda localmente, sem API externa.
"""
import logging
import queue
import time
from typing import Optional

import numpy as np


class SpeechToText:
    def __init__(
        self,
        model_name: str = "base",
        language: str = "pt",
        device: str = "cpu",
        compute_type: str = "int8",
        logger: Optional[logging.Logger] = None,
    ):
        self.model_name = model_name
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self.logger = logger
        self._model = None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
        if self.logger:
            self.logger.info(
                f"Whisper model loaded: {self.model_name} ({self.device}/{self.compute_type})"
            )

    def transcribe(self, audio: np.ndarray) -> str:
        if audio is None or len(audio) == 0:
            return ""
        self._ensure_model()
        segments, _info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            vad_filter=True,
        )
        text = " ".join(segment.text for segment in segments).strip()
        if self.logger:
            self.logger.info(f"Transcribed ({len(audio) / 16000:.1f}s): {text[:120]}")
        return text

    def listen(
        self,
        sample_rate: int = 16000,
        silence_limit: float = 1.5,
        max_duration: float = 20.0,
        speech_timeout: float = 10.0,
        rms_threshold: float = 0.01,
    ) -> Optional[str]:
        """Grava do microfone ate o silencio e retorna a transcricao.

        Retorna None se nenhuma fala for detectada dentro de `speech_timeout`
        segundos (util para o loop continuar sem travar).
        """
        import sounddevice as sd

        q: queue.Queue[np.ndarray] = queue.Queue()

        def callback(indata, _frames, _time, _status) -> None:
            q.put(indata[:, 0].copy())

        if self.logger:
            self.logger.info(
                f"Listening (timeout={speech_timeout:.0f}s, silence={silence_limit:.1f}s)..."
            )

        frames: list = []
        speech_start: Optional[float] = None
        started = time.monotonic()

        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            callback=callback,
        ):
            while True:
                block = q.get()
                now = time.monotonic()
                rms = float(np.sqrt(np.mean(block**2)))

                if rms >= rms_threshold:
                    frames.append(block)
                    if speech_start is None:
                        speech_start = now
                elif speech_start is not None:
                    frames.append(block)
                    if now - speech_start >= silence_limit:
                        break

                if speech_start is None and now - started >= speech_timeout:
                    if self.logger:
                        self.logger.info("No speech detected within timeout")
                    return None
                if now - started >= max_duration:
                    break

        if not frames:
            return None

        audio = np.concatenate(frames)
        text = self.transcribe(audio)
        return text or None
