"""Sintese de voz (Text-to-Speech) com voz neural humana via edge-tts.

O edge-tts usa as vozes neurais da Microsoft Edge (ex: pt-BR-FranciscaNeural),
que soam naturais e nao roboticas. O audio MP3 gerado e reproduzido com
`miniaudio` + `sounddevice` (fallback para `pygame`).
"""
import asyncio
import io
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional


class TextToSpeech:
    def __init__(
        self,
        voice: str = "pt-BR-FranciscaNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        output_dir: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.output_dir = output_dir
        self.logger = logger

    def synthesize(self, text: str) -> bytes:
        import edge_tts

        async def _collect() -> bytes:
            communicate = edge_tts.Communicate(
                text, self.voice, rate=self.rate, volume=self.volume
            )
            chunks = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.extend(chunk["data"])
            return bytes(chunks)

        return asyncio.run(_collect())

    def speak(self, text: str) -> bool:
        """Gera e reproduz a fala. Retorna False em qualquer falha (nao lanca)."""
        if not text or not text.strip():
            return False

        try:
            audio = self.synthesize(text)
        except Exception as e:
            if self.logger:
                self.logger.error(f"TTS synthesis failed: {e}")
            return False

        if not audio:
            if self.logger:
                self.logger.warning("TTS returned empty audio")
            return False

        if self.output_dir:
            try:
                path = Path(self.output_dir)
                path.mkdir(parents=True, exist_ok=True)
                file_path = path / f"answer_{int(time.time())}.mp3"
                file_path.write_bytes(audio)
                if self.logger:
                    self.logger.info(f"Audio saved: {file_path}")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Could not save audio: {e}")

        try:
            self._play(audio)
            return True
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Playback failed: {e} (instale 'miniaudio' ou 'pygame')"
                )
            return False

    def _play(self, audio: bytes) -> None:
        try:
            import miniaudio
            import sounddevice as sd

            sample = miniaudio.decode_fp(io.BytesIO(audio))
            sd.play(sample.samples, samplerate=sample.sample_rate)
            sd.wait()
            return
        except ImportError:
            pass

        try:
            import pygame

            pygame.mixer.init()
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio)
                tmp = f.name
            pygame.mixer.music.load(tmp)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(50)
            os.unlink(tmp)
            return
        except ImportError:
            pass

        raise RuntimeError("no audio playback backend available")
