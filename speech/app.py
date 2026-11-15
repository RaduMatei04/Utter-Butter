"""
Serviciul `speech`: lanțul complet al recunoașterii vocale.

  POST /api/command?method=whisper|dtw&preprocess=1
      corp: formular cu un câmp "audio" = fișier WAV (mono, 16 kHz, 16 biți)
      răspuns: {"action", "value", "transcript", "language", "method",
                "speech_detected", "speech_ms", "processing_ms", ...}

  Înregistrări (pagina #/record din aplicație):
  GET    /api/speech/recordings?set=templates|test&condition=quiet|noise
  POST   /api/speech/recordings?set=...&action=next&condition=...   (+ fișier "audio")
  DELETE /api/speech/recordings/last?set=...&action=next&condition=...

Lanțul:
  WAV -> numpy -> eliminare DC -> VAD (energie + ZCR) -> tăiere liniște -> normalizare
      -> metoda A: Whisper (text) -> interpretare (comandă)
      -> metoda B: pre-emphasis -> MFCC -> DTW cu șabloanele -> comandă
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

# Dacă e setat, fiecare comandă primită se salvează ca WAV în acest folder.
RECORDINGS_DIR = os.environ.get("SAVE_RECORDINGS_DIR")
# Setul de test pentru evaluare: <DATASET_DIR>/<condiție>/<acțiune>/*.wav
DATASET_DIR = Path(os.environ.get("DATASET_DIR", "/evaluation/data"))
CONDITIONS = ("quiet", "noise")

# La pornire: modelul Whisper se încarcă în fundal, iar șabloanele DTW imediat
threading.Thread(target=recognizer_whisper.load_model, daemon=True).start()
recognizer_dtw.load_templates()


def timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]


def save_recording(data, action):
    """Salvează WAV-ul primit, cu ora și comanda recunoscută în nume."""
    if not RECORDINGS_DIR:
        return
    folder = Path(RECORDINGS_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{timestamp()}_{action}.wav").write_bytes(data)


# ======================================================================
# Comenzi vocale
# ======================================================================

@app.get("/api/speech/health")
def health():
    return jsonify({
        "status": "ok",
        "model_ready": recognizer_whisper.is_ready(),
        "dtw_templates": recognizer_dtw.template_counts(),
    })


@app.post("/api/command")
def command():
    start_time = time.perf_counter()  # cronometrăm toată prelucrarea
    method = request.args.get("method", "whisper")
    use_vad = request.args.get("preprocess", "1") != "0"

    if method not in ("whisper", "dtw"):
        return jsonify({"error": "method must be 'whisper' or 'dtw'"}), 400

    # 1. Primim fișierul audio
    audio_file = request.files.get("audio")
    if audio_file is None:
        return jsonify({"error": "Missing 'audio' file"}), 400
    data = audio_file.read()

    # 2. WAV -> vector numpy cu valori în [-1, 1]
    try:
        signal = load_wav(data)
    except Exception as error:  # fișier stricat sau în alt format
        return jsonify({"error": f"Invalid WAV: {error}"}), 400

    if method == "whisper" and not recognizer_whisper.is_ready():
        # 503 = „serviciu indisponibil momentan”; browserul încearcă din nou mai târziu
        return jsonify({"error": "Speech model is still loading"}), 503
    if method == "dtw" and not recognizer_dtw.has_templates():
        return jsonify({"error": "No DTW templates yet. Record some at #/record"}), 503

    # 3. Preprocesare: DC, VAD (energie + ZCR), tăierea liniștii, normalizare
    clean, _ = preprocess(signal, use_vad=use_vad)

    response = {"method": method, "value": None, "language": None,
                "speech_detected": clean is not None, "speech_ms": 0}

    if clean is None:
        # VAD-ul nu a găsit vorbire (zgomot, clic, tuse): nu mai recunoaștem nimic
        response.update(action="unknown", transcript="")
    else:
        response["speech_ms"] = round(len(clean) / SAMPLE_RATE * 1000)

        if method == "whisper":
            # 4A. Whisper: semnal -> text, apoi text -> comandă
            transcript, language = recognizer_whisper.transcribe(clean)
            result = interpret(transcript)
            response.update(action=result["action"], value=result["value"],
                            transcript=transcript, language=language)
        else:
            # 4B. MFCC + DTW: semnal -> cel mai apropiat șablon
            result = recognizer_dtw.recognize(clean)
            response.update(
                action=result["action"],
                transcript=f"(DTW) {result['action']}, distance {result['distance']}",
                distance=result["distance"],
                threshold=result["threshold"],
                scores=result["scores"],
            )

    response["processing_ms"] = round((time.perf_counter() - start_time) * 1000)
    print(
        f"[command:{method}] speech {response['speech_ms']} ms | "
        f"{response['transcript']!r} -> {response['action']} ({response['processing_ms']} ms)",
        flush=True,
    )
    save_recording(data, response["action"])
    return jsonify(response)


# ======================================================================
# Înregistrarea șabloanelor DTW și a setului de test
# ======================================================================

def target_folder(args):
    """Folderul în care se salvează o înregistrare, din parametrii cererii.
    Ridică ValueError dacă parametrii sunt greșiți."""
    set_name = args.get("set", "templates")
    action = args.get("action")
    if action is not None and action not in COMMANDS:
        raise ValueError(f"Unknown action '{action}'")

    if set_name == "templates":
        base = recognizer_dtw.TEMPLATES_DIR
    elif set_name == "test":
        condition = args.get("condition", "quiet")
        if condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {CONDITIONS}")
        base = DATASET_DIR / condition
    else:
        raise ValueError("set must be 'templates' or 'test'")

    return base if action is None else base / action


def count_recordings(base):
    """Câte fișiere WAV există pentru fiecare acțiune."""
    return {
        action: len(list((base / action).glob("*.wav"))) if (base / action).exists() else 0
        for action in COMMANDS
    }


@app.get("/api/speech/recordings")
def list_recordings():
    try:
        base = target_folder({**request.args, "action": None})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(count_recordings(base))


@app.post("/api/speech/recordings")
def add_recording():
    try:
        folder = target_folder(request.args)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if not request.args.get("action"):
        return jsonify({"error": "Missing 'action'"}), 400

    audio_file = request.files.get("audio")
    if audio_file is None:
        return jsonify({"error": "Missing 'audio' file"}), 400
    data = audio_file.read()

    # Verificăm că e un WAV bun și că VAD-ul găsește vorbire în el
    try:
        clean, _ = preprocess(load_wav(data))
    except Exception as error:
        return jsonify({"error": f"Invalid WAV: {error}"}), 400
    if clean is None:
        return jsonify({"error": "No speech detected, please try again"}), 422

    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{timestamp()}.wav").write_bytes(data)

    if request.args.get("set", "templates") == "templates":
        recognizer_dtw.load_templates()  # noile șabloane se folosesc imediat

    return jsonify(count_recordings(folder.parent))


@app.delete("/api/speech/recordings/last")
def delete_last_recording():
    """Șterge cea mai nouă înregistrare a unei comenzi (pentru „Undo”)."""
    try:
        folder = target_folder(request.args)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    files = sorted(folder.glob("*.wav")) if folder.exists() else []
    if not files:
        return jsonify({"error": "Nothing to delete"}), 404
    files[-1].unlink()

    if request.args.get("set", "templates") == "templates":
        recognizer_dtw.load_templates()

    return jsonify(count_recordings(folder.parent))
