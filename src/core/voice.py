"""
Alerta por voz (F7·C3 - Da fala ao texto e do texto à fala / TTS).
Tenta sintetizar áudio com pyttsx3; se indisponível, grava a transcrição em
.txt (fallback). Mantém a integração de 'voz' demonstrável em qualquer ambiente.
"""
from pathlib import Path
from config import DATA_DIR

ALERT_DIR = DATA_DIR / "alerts"
ALERT_DIR.mkdir(parents=True, exist_ok=True)


def falar_alerta(texto, nome="alerta"):
    wav = ALERT_DIR / f"{nome}.wav"
    try:
        import pyttsx3
        eng = pyttsx3.init()
        eng.save_to_file(texto, str(wav))
        eng.runAndWait()
        return {"engine": "pyttsx3", "path": str(wav)}
    except Exception:
        txt = ALERT_DIR / f"{nome}.txt"
        Path(txt).write_text(texto, encoding="utf-8")
        return {"engine": "texto-fallback", "path": str(txt)}
