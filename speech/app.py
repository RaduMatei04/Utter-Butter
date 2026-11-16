"""
Serviciul `speech`: primește audio și răspunde cu comanda recunoscută.

  POST /api/command?method=whisper|dtw&preprocess=1|0
       fișier "audio" (WAV mono 16 kHz) -> {"action", "value", "transcript", ...}

  Pentru pagina #/record (șabloane DTW și set de test):
  GET    /api/speech/recordings?set=templates|test&condition=quiet|noise
  POST   /api/speech/recordings?set=...&condition=...&action=next   (+ fișier "audio")
  DELETE /api/speech/recordings/last?set=...&condition=...&action=next
"""

import os
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request

import recognizer_dtw
import recognizer_whisper
from commands import COMMANDS, interpret
from preprocessing import SAMPLE_RATE, load_wav, preprocess

app = Flask(__name__)

RECORDINGS_DIR = os.environ.get("SAVE_RECORDINGS_DIR")                   # fiecare comandă primită
DATASET_DIR = Path(os.environ.get("DATASET_DIR", "/evaluation/data"))    # setul de test

# La pornire: Whisper se încarcă în fundal (durează câteva secunde), șabloanele DTW imediat
threading.Thread(target=recognizer_whisper.load_model).start()
recognizer_dtw.load_templates()


def now():
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


@app.get("/api/speech/health")
def health():
    return {"model_ready": recognizer_whisper.is_ready(), "dtw_templates": recognizer_dtw.template_counts()}


# ======================================================================
# Comanda vocală
# ======================================================================

@app.post("/api/command")
def command():
    start = time.perf_counter()
    method = request.args.get("method", "whisper")
    use_vad = request.args.get("preprocess", "1") == "1"

    # 1. Citim fișierul audio
    data = request.files["audio"].read()
    try:
        signal = load_wav(data)
    except Exception as error:
        return {"error": f"Invalid WAV: {error}"}, 400

    if method == "whisper" and not recognizer_whisper.is_ready():
        return {"error": "Speech model is still loading"}, 503
    if method == "dtw" and not recognizer_dtw.templates:
        return {"error": "No DTW templates yet. Record some at #/record"}, 503

    # 2. Preprocesare: DC, VAD, tăierea liniștii, normalizare
    clean = preprocess(signal, use_vad)
    result = {"method": method, "action": "unknown", "value": None, "transcript": ""}

    # 3. Recunoaștere (dacă VAD-ul a găsit vorbire)
    if clean is not None and method == "whisper":
        text, language = recognizer_whisper.transcribe(clean)
        result.update(interpret(text), transcript=text, language=language)
    elif clean is not None and method == "dtw":
        dtw = recognizer_dtw.recognize(clean)
        result.update(dtw, transcript=f"(DTW) {dtw['action']}, distance {dtw['distance']}")

    result["speech_ms"] = 0 if clean is None else round(len(clean) / SAMPLE_RATE * 1000)
    result["processing_ms"] = round((time.perf_counter() - start) * 1000)
    print(f"[{method}] {result['transcript']!r} -> {result['action']} ({result['processing_ms']} ms)", flush=True)

    # 4. Salvăm înregistrarea (pentru grafice și depanare)
    if RECORDINGS_DIR:
        Path(RECORDINGS_DIR).mkdir(parents=True, exist_ok=True)
        Path(RECORDINGS_DIR, f"{now()}_{result['action']}.wav").write_bytes(data)

    return jsonify(result)


# ======================================================================
# Înregistrări pentru șabloane DTW și setul de test
# ======================================================================

def recordings_folder():
    """Folderul ales prin parametrii cererii: șabloanele DTW sau setul de test."""
    if request.args.get("set") == "test":
        condition = request.args.get("condition", "quiet")
        if condition not in ("quiet", "noise"):
            raise ValueError("condition must be 'quiet' or 'noise'")
        return DATASET_DIR / condition
    return recognizer_dtw.TEMPLATES_DIR


def count_per_command(folder):
    return {action: len(list((folder / action).glob("*.wav"))) for action in COMMANDS}


@app.get("/api/speech/recordings")
def list_recordings():
    return count_per_command(recordings_folder())


@app.post("/api/speech/recordings")
def add_recording():
    folder = recordings_folder()
    action = request.args.get("action")
    if action not in COMMANDS:
        return {"error": "Unknown command"}, 400

    data = request.files["audio"].read()
    if preprocess(load_wav(data)) is None:
        return {"error": "No speech detected, please try again"}, 422

    (folder / action).mkdir(parents=True, exist_ok=True)
    (folder / action / f"{now()}.wav").write_bytes(data)
    if folder == recognizer_dtw.TEMPLATES_DIR:
        recognizer_dtw.load_templates()   # șablonul nou se folosește imediat
    return count_per_command(folder)


@app.delete("/api/speech/recordings/last")
def delete_last_recording():
    folder = recordings_folder()
    files = sorted((folder / request.args.get("action", "")).glob("*.wav"))
    if files:
        files[-1].unlink()   # cel mai nou fișier (numele începe cu data și ora)
    if folder == recognizer_dtw.TEMPLATES_DIR:
        recognizer_dtw.load_templates()
    return count_per_command(folder)


@app.errorhandler(ValueError)
def bad_request(error):
    return {"error": str(error)}, 400
