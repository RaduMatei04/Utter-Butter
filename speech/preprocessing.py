"""
preprocessing.py: pregătirea semnalului vocal înainte de recunoaștere.

Pașii, în ordine:
  1. load_wav       fișierul WAV devine o listă de numere între -1 și 1
  2. remove_dc      scădem media semnalului
  3. detect_speech  VAD: găsim unde se vorbește (energie + ZCR, pe cadre de 25 ms)
  4. tăiem liniștea de la început și de la sfârșit
  5. normalize      cel mai mare vârf devine 0.95

Separat, pre_emphasis() e un filtru folosit doar pentru MFCC (nu înainte de Whisper).
"""

import io
import wave

import numpy as np

SAMPLE_RATE = 16000   # eșantioane pe secundă

FRAME = 400           # un cadru = 25 ms (400 de eșantioane la 16 kHz)
HOP = 160             # pasul dintre cadre = 10 ms (cadrele se suprapun)

# Parametrii VAD
LOW_MARGIN_DB = 6         # pragul de jos  = zgomotul de fond + 6 dB
HIGH_MARGIN_DB = 12       # pragul de sus  = zgomotul de fond + 12 dB
MIN_LEVEL_DB = -50        # sub -50 dB e liniște, oricât de liniștită ar fi camera
ZCR_THRESHOLD = 0.25      # peste acest ZCR, un cadru slab poate fi „s”, „f”, „ș”
MIN_SPEECH_FRAMES = 10    # sub 10 cadre (100 ms) de vorbire = zgomot (clic, tuse)
MARGIN = 2400             # păstrăm 150 ms (2400 de eșantioane) înainte și după vorbire


def load_wav(data):
    """Bytes WAV (mono, 16 kHz, 16 biți) -> vector numpy cu valori în [-1, 1]."""
    with wave.open(io.BytesIO(data), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != SAMPLE_RATE:
            raise ValueError("Audio must be mono, 16-bit, 16 kHz")
        raw = wav.readframes(wav.getnframes())

    # Fiecare eșantion e un întreg între -32768 și 32767; împărțim la 32768
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    return samples / 32768.0


def load_wav_file(path):
    with open(path, "rb") as f:
        return load_wav(f.read())


def remove_dc(signal):
    """Componenta continuă (DC) = un decalaj constant al microfonului. O eliminăm scăzând media."""
    return signal - np.mean(signal)


def normalize(signal):
    """Aducem cel mai mare vârf la 0.95, ca vocea să aibă mereu același volum."""
    peak = np.max(np.abs(signal))
    return signal if peak == 0 else signal / peak * 0.95


def pre_emphasis(signal, alpha=0.97):
    """Filtru trece-sus:  y[n] = x[n] - 0.97 · x[n-1]
    Accentuează frecvențele înalte (consoanele), utile pentru MFCC."""
    result = signal.copy()
    result[1:] = signal[1:] - alpha * signal[:-1]
    return result


def split_into_frames(signal):
    """Împarte semnalul în cadre de 25 ms, cu pas de 10 ms.
    Rezultatul e o matrice: un rând = un cadru (400 de eșantioane)."""
    if len(signal) < FRAME:
        signal = np.pad(signal, (0, FRAME - len(signal)))   # completăm cu zerouri
    count = 1 + (len(signal) - FRAME) // HOP
    return np.array([signal[i * HOP: i * HOP + FRAME] for i in range(count)])


def frame_energy_db(frames):
    """Energia pe termen scurt a fiecărui cadru, în decibeli:
        E = (1/N) · Σ x[n]²       ->      10 · log10(E)"""
    energy = np.mean(frames ** 2, axis=1)
    return 10 * np.log10(energy + 1e-10)   # +1e-10 ca să nu calculăm log(0)


def frame_zcr(frames):
    """Rata trecerilor prin zero = cât de des își schimbă semnalul semnul.
    Două eșantioane vecine au semne diferite <=> produsul lor e negativ.
      vocale: ZCR mic (~0.1)   consoane s/f/ș: ZCR mare (~0.4)"""
    sign_changes = frames[:, 1:] * frames[:, :-1] < 0
    return np.mean(sign_changes, axis=1)


def detect_speech(signal):
    """VAD (Voice Activity Detection): unde e vorbire în semnal?

    Un cadru e VORBIRE dacă:
      - energia lui e peste pragul de SUS (voce clară), SAU
      - energia e peste pragul de JOS și ZCR e mare (consoană „șuierată”, ex. „s”).
    Pragurile pornesc de la zgomotul de fond = energia celor mai liniștite 10% din cadre.

    Întoarce un dicționar cu tot ce am calculat (îl folosim și la grafice)."""
    frames = split_into_frames(signal)
    energy_db = frame_energy_db(frames)
    zcr = frame_zcr(frames)

    noise_db = np.percentile(energy_db, 10)
    low_db = max(noise_db + LOW_MARGIN_DB, MIN_LEVEL_DB)
    high_db = max(noise_db + HIGH_MARGIN_DB, MIN_LEVEL_DB)

    is_speech = (energy_db > high_db) | ((energy_db > low_db) & (zcr > ZCR_THRESHOLD))
    speech_frames = np.flatnonzero(is_speech)   # indicii cadrelor cu vorbire

    vad = {
        "energy_db": energy_db, "zcr": zcr, "is_speech": is_speech,
        "noise_db": noise_db, "low_db": low_db, "high_db": high_db,
        "has_speech": len(speech_frames) >= MIN_SPEECH_FRAMES,
        "start": 0, "end": 0,
    }
    if vad["has_speech"]:
        # de la primul cadru cu vorbire până la ultimul, plus o margine
        vad["start"] = max(0, speech_frames[0] * HOP - MARGIN)
        vad["end"] = min(len(signal), speech_frames[-1] * HOP + FRAME + MARGIN)
    return vad


def preprocess(signal, use_vad=True):
    """Tot lanțul. Întoarce semnalul curat sau None dacă nu e vorbire.
    use_vad=False sare peste VAD (folosit în evaluare, pentru comparație)."""
    signal = remove_dc(signal)
    if use_vad:
        vad = detect_speech(signal)
        if not vad["has_speech"]:
            return None
        signal = signal[vad["start"]:vad["end"]]
    return normalize(signal).astype(np.float32)
