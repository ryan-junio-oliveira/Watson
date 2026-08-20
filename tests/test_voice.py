from unittest.mock import MagicMock, patch

import numpy as np

from voice.stt import SpeechToText
from voice.tts import TextToSpeech


class TestSpeechToText:
    def test_transcribe_empty_returns_empty(self):
        stt = SpeechToText()
        assert stt.transcribe(np.array([], dtype=np.float32)) == ""

    def test_transcribe_uses_whisper(self):
        stt = SpeechToText()
        fake_segment = MagicMock(text="ola watson")
        fake_model = MagicMock()
        fake_model.transcribe.return_value = ([fake_segment], None)
        with patch.object(stt, "_ensure_model"):
            stt._model = fake_model
            result = stt.transcribe(np.zeros(16000, dtype=np.float32))
        assert result == "ola watson"
        fake_model.transcribe.assert_called_once()
        assert fake_model.transcribe.call_args.kwargs["language"] == "pt"

    def test_listen_returns_none_without_audio(self):
        import sys
        import types

        stt = SpeechToText()
        fake_sd = types.ModuleType("sounddevice")
        fake_sd.InputStream = MagicMock(return_value=MagicMock())
        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            with patch("voice.stt.queue.Queue.get") as get:
                get.side_effect = [np.zeros(256, dtype=np.float32)]
                with patch("voice.stt.time.monotonic") as t:
                    t.side_effect = [0.0, 11.0]
                    assert stt.listen(speech_timeout=1.0) is None

    def test_trim_silence_removes_edges(self):
        audio = np.zeros(16000, dtype=np.float32)
        audio[4000:12000] = 0.5
        trimmed = SpeechToText._trim_silence(audio)
        assert len(trimmed) < len(audio)
        assert float(np.abs(trimmed).max()) > 0.0


class TestTextToSpeech:
    def test_speak_empty_returns_false(self):
        tts = TextToSpeech()
        assert tts.speak("") is False
        assert tts.speak("   ") is False

    def test_speak_returns_false_on_synthesis_error(self):
        tts = TextToSpeech()
        with patch.object(tts, "synthesize", side_effect=RuntimeError("boom")):
            assert tts.speak("ola") is False

    def test_speak_plays_audio(self):
        tts = TextToSpeech()
        with patch.object(tts, "synthesize", return_value=b"mp3data"), patch.object(
            tts, "_play"
        ) as play:
            assert tts.speak("ola") is True
            play.assert_called_once_with(b"mp3data")

    def test_speak_saves_audio_when_output_dir(self, tmp_path):
        tts = TextToSpeech(output_dir=str(tmp_path))
        with patch.object(tts, "synthesize", return_value=b"mp3data"), patch.object(
            tts, "_play"
        ):
            assert tts.speak("ola") is True
        files = list(tmp_path.glob("*.mp3"))
        assert len(files) == 1
        assert files[0].read_bytes() == b"mp3data"
