"""
recognizer_whisper.py: speech-to-text cu Whisper (prin biblioteca faster-whisper).

Whisper este o rețea neuronală (encoder-decoder, de tip Transformer) antrenată
de OpenAI pe ~680.000 de ore de vorbire. Primește semnalul audio la 16 kHz,
calculează intern o spectrogramă log-Mel și generează textul.
Rulează LOCAL, pe procesor, fără internet (doar prima dată descarcă modelul).
"""

import os
import threading

from faster_whisper import WhisperModel

# Modelul: "tiny" (cel mai rapid), "base" (echilibrat), "small" (mai precis, mai lent)
MODEL_NAME = os.environ.get("WHISPER_MODEL", "base")
# Folderul unde se salvează modelul descărcat (un volum Docker, ca să nu-l descărcăm iar)
MODEL_DIR = os.environ.get("WHISPER_DIR", "/models")

# Comenzile pot fi în engleză sau română
ALLOWED_LANGUAGES = ("en", "ro")

# Dacă Whisper crede că un fragment NU conține vorbire cu probabilitate mai mare
# de atât, îl ignorăm. (Pe zgomot, Whisper poate „inventa” fraze, de ex. „Thank you.”)
NO_SPEECH_THRESHOLD = 0.6

_model = None
_lock = threading.Lock()  # un singur fragment procesat odată


def load_model():
    """Încarcă modelul în memorie (durează câteva secunde; prima dată și descărcarea)."""
    global _model
    with _lock:
        if _model is None:
            print(f"[whisper] Loading model '{MODEL_NAME}'...", flush=True)
            # int8 = numere pe 8 biți: mai rapid și mai puțină memorie pe CPU
            _model = WhisperModel(
                MODEL_NAME, device="cpu", compute_type="int8", download_root=MODEL_DIR
            )
            print("[whisper] Model ready.", flush=True)
    return _model


def is_ready():
    return _model is not None


def _run(model, signal, language):
    """O rulare a lui Whisper. Întoarce (text, info)."""
    segments, info = model.transcribe(
        signal,
        language=language,              # None = detectează automat limba
        beam_size=1,                    # căutare simplă (greedy): mai rapid
        temperature=0.0,
        condition_on_previous_text=False,
        without_timestamps=True,
        vad_filter=False,               # VAD-ul îl facem noi (pasul 5)
    )
    # `segments` e un generator: transcrierea se face efectiv aici
    text_parts = [s.text for s in segments if s.no_speech_prob < NO_SPEECH_THRESHOLD]
    return "".join(text_parts).strip(), info


def transcribe(signal):
    """Semnal (numpy float32, 16 kHz) -> (text, limba)."""
    model = load_model()
    with _lock:
        text, info = _run(model, signal, None)
        language = info.language

        # Pe fragmente scurte, detecția automată a limbii greșește uneori
        # (ex: „next” recunoscut ca germană). Atunci alegem dintre engleză și
        # română limba cea mai probabilă și rulăm încă o dată.
        if language not in ALLOWED_LANGUAGES:
            probabilities = dict(info.all_language_probs or [])
            language = max(ALLOWED_LANGUAGES, key=lambda lang: probabilities.get(lang, 0))
            text, _ = _run(model, signal, language)

    return text, language
