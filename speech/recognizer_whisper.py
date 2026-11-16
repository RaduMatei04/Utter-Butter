"""
recognizer_whisper.py: metoda A, Whisper (semnal -> text).

Whisper e o rețea neuronală (Transformer) antrenată de OpenAI pe ~680.000 de ore
de vorbire. Primește semnalul la 16 kHz și scrie textul. Rulează local, pe procesor.
"""

import os

from faster_whisper import WhisperModel

model = None   # se încarcă o singură dată, la pornirea serverului


def load_model():
    global model
    if model is None:
        print("[whisper] Loading model...", flush=True)
        model = WhisperModel(
            os.environ.get("WHISPER_MODEL", "base"),       # tiny / base / small
            device="cpu", compute_type="int8",             # int8 = mai rapid pe procesor
            download_root=os.environ.get("WHISPER_DIR", "/models"),
        )
        print("[whisper] Model ready.", flush=True)


def is_ready():
    return model is not None


def run_whisper(signal, language):
    segments, info = model.transcribe(
        signal,
        language=language,                 # None = Whisper ghicește singur limba
        beam_size=1,                       # căutare simplă = mai rapid
        vad_filter=False,                  # VAD-ul îl facem noi (preprocessing.py)
        condition_on_previous_text=False,
    )
    # Pe zgomot, Whisper „inventează” uneori fraze („Thank you.”).
    # Păstrăm doar bucățile în care e sigur că s-a vorbit.
    text = " ".join(s.text for s in segments if s.no_speech_prob < 0.6)
    return text.strip(), info


def transcribe(signal):
    """Semnal (numpy, 16 kHz) -> (text, limba)."""
    text, info = run_whisper(signal, language=None)

    # Pe fraze scurte, Whisper poate ghici greșit limba (ex: „next” = germană).
    # Atunci alegem engleza sau româna, care e mai probabilă, și încercăm din nou.
    if info.language not in ("en", "ro"):
        probabilities = dict(info.all_language_probs or [])
        language = "ro" if probabilities.get("ro", 0) > probabilities.get("en", 0) else "en"
        text, info = run_whisper(signal, language)

    return text, info.language
