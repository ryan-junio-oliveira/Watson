"""Autoteste do modo voz.

Roda `python app.py --voice-test` para verificar, passo a passo, se o
microfone (STT) e a saida de voz (TTS) estao funcionando.
"""
from typing import Optional

import numpy as np


def check_imports() -> dict:
    """Verifica se as dependencias de voz estao instaladas."""
    result = {}
    for mod in ("faster_whisper", "sounddevice", "edge_tts", "miniaudio"):
        try:
            __import__(mod)
            result[mod] = "OK"
        except ImportError as e:
            result[mod] = f"FALTANDO ({e})"
    return result


def list_devices() -> None:
    try:
        import sounddevice as sd

        print("\n[1/4] Dispositivos de audio:")
        print(f"  Entrada (mic)  : {sd.query_devices(kind='input')}")
        print(f"  Saida (alto-falante): {sd.query_devices(kind='output')}")
    except Exception as e:
        print(f"  Nao foi possivel listar dispositivos: {e}")


def test_mic(duration: float = 2.0, sample_rate: int = 16000) -> Optional[float]:
    """Grava um trecho e mede o RMS. > 0 retorna que o mic captou audio."""
    try:
        import sounddevice as sd

        print(f"\n[2/4] Gravando {duration:.0f}s de audio para testar o microfone...")
        print("      (fale algo ou bata palma enquanto grava)")
        audio = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        rms = float(np.sqrt(np.mean(audio**2)))
        status = "captando audio" if rms > 0.005 else "SILENCIO (mic nao esta captando?)"
        print(f"      Nivel de audio captado: {rms:.4f} -> {status}")
        return rms
    except Exception as e:
        print(f"      Erro ao gravar: {e}")
        return None


def test_tts(text: str = "Olá! Eu sou o Watson. O modo de voz está funcionando.") -> bool:
    """Gera e reproduz uma frase de teste com a voz configurada."""
    from voice.tts import TextToSpeech

    tts = TextToSpeech()
    print(f"\n[3/4] Reproduzindo fala de teste: '{text}'")
    print(f"      Voz: {tts.voice}")
    ok = tts.speak(text)
    print("      Fala reproduzida com sucesso." if ok else "      FALHA ao reproduzir fala.")
    return ok


def test_stt() -> Optional[str]:
    """Ouve uma pergunta e transcreve (usa a fala do teste anterior para validar)."""
    from voice.stt import SpeechToText

    stt = SpeechToText()
    print("\n[4/4] Teste de transcricao (Whisper): fale 'Olá Watson' no microfone")
    print("      (aguardando ate 10s...)", flush=True)
    text = stt.listen()
    if text:
        print(f"      Transcricao: '{text}'")
    else:
        print("      Nenhuma fala detectada (o teste anterior ja valida o mic).")
    return text


def run_self_test() -> None:
    print("=" * 60)
    print("  AUTOTESTE DO MODO VOZ")
    print("=" * 60)

    imports = check_imports()
    print("\n[0/4] Dependencias:")
    for mod, status in imports.items():
        mark = "[OK] " if status == "OK" else "[!!] "
        print(f"  {mark}{mod}: {status}")
    missing = [m for m, s in imports.items() if s != "OK"]
    if missing:
        print(f"\nFaltam dependencias: {', '.join(missing)}")
        print("Rode: pip install faster-whisper sounddevice edge-tts miniaudio")
        return

    list_devices()
    test_mic()
    test_tts()
    test_stt()

    print("\n" + "=" * 60)
    print("  Autoteste concluido. Se viu nivel de audio e ouviu a fala,")
    print("  o modo voz esta funcionando. Rode 'python app.py' e fale.")
    print("=" * 60)
