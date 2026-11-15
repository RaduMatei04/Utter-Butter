"""
preprocessing.py: încărcarea și preprocesarea semnalului vocal.

Toate calculele sunt scrise EXPLICIT cu numpy (fără funcții „cutie neagră”),
ca să poată fi explicate în documentație.

Lanțul folosit de serviciul `speech`:

    WAV (16 kHz, mono)
      │  load_wav()            -> vector numpy, valori în [-1, 1]
      │  remove_dc()           -> scădem media (componenta continuă)
      │  detect_speech()       -> VAD: energie pe termen scurt + ZCR, pe cadre de 25 ms
      │                           (dacă nu e vorbire, ne oprim aici)
      │  trim                  -> păstrăm doar zona cu vorbire (+ o mică margine)
      │  normalize()           -> vârful semnalului devine 0.95
      ▼
    semnal curat -> Whisper
                 -> pre_emphasis() -> MFCC -> DTW (pasul 6)

De ce pre-emphasis NU se aplică înainte de Whisper:
  pre-emphasis accentuează frecvențele înalte, ceea ce ajută la calculul
  trăsăturilor spectrale (MFCC). Whisper însă a fost antrenat pe vorbire
  „naturală” și își calculează singur spectrograma, deci îi dăm semnalul
  fără pre-emphasis. (Efectul se poate verifica în evaluate.py.)
"""

import io
import wave

import numpy as np

SAMPLE_RATE = 16000   # Hz: frecvența de eșantionare (o cere și Whisper)

# --- Parametrii analizei pe cadre ---
FRAME_MS = 25         # lungimea unui cadru: 25 ms = 400 de eșantioane
HOP_MS = 10           # pasul între cadre: 10 ms = 160 de eșantioane (cadrele se suprapun)

# --- Parametrii VAD (detecția activității vocale) ---
PRE_EMPHASIS = 0.97   # coeficientul filtrului y[n] = x[n] - 0.97·x[n-1]
NOISE_PERCENTILE = 10     # zgomotul de fond = nivelul celor mai liniștite 10% din cadre
LOW_MARGIN_DB = 6         # pragul de jos:  zgomot + 6 dB
HIGH_MARGIN_DB = 12       # pragul de sus:  zgomot + 12 dB
MIN_SPEECH_DB = -50       # sub -50 dBFS e liniște, oricât de „liniștit” ar fi zgomotul
ZCR_THRESHOLD = 0.25      # peste acest ZCR, un cadru slab poate fi o consoană fricativă (s, f, ș)
MIN_SPEECH_MS = 100       # zone de vorbire mai scurte = zgomot (clic, pocnet)
MAX_GAP_MS = 200          # pauzele mai scurte dintre cuvinte NU taie vorbirea
MARGIN_MS = 150           # păstrăm 150 ms înainte și după vorbire
                          # (cu 50 ms, în zgomot, VAD-ul tăia finalul cuvintelor slabe:
                          #  „ingredients” -> „in”, „read” -> „Re-”; vezi evaluate.py)


# ======================================================================
# 1. Încărcare
# ======================================================================

def load_wav(data):
    """Citește un fișier WAV (bytes) și îl transformă într-un vector numpy.

    Formatul așteptat (îl produce listener.js din browser):
      mono, 16 kHz, 16 biți pe eșantion (PCM, întregi între -32768 și 32767).

    Întoarce un vector float32 cu valori în intervalul [-1, 1].
    """
    with wave.open(io.BytesIO(data), "rb") as wav:
        if wav.getnchannels() != 1:
            raise ValueError("Audio must be mono")
        if wav.getsampwidth() != 2:
            raise ValueError("Audio must be 16-bit PCM")
        if wav.getframerate() != SAMPLE_RATE:
            raise ValueError(f"Audio must be {SAMPLE_RATE} Hz")
        raw = wav.readframes(wav.getnframes())

    # '<i2' = întreg cu semn pe 2 octeți, little-endian (formatul WAV)
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    return samples / 32768.0  # împărțim la 2^15 => valori în [-1, 1]


def load_wav_file(path):
    """La fel ca load_wav(), dar citește direct dintr-un fișier de pe disc."""
    with open(path, "rb") as f:
        return load_wav(f.read())


# ======================================================================
# 2. Filtre simple
# ======================================================================

def remove_dc(signal):
    """Elimină componenta continuă (DC offset): scădem media semnalului.
    Un microfon poate avea un mic decalaj constant față de zero; el nu
    conține informație vocală, dar mărește artificial energia cadrelor."""
    return signal - np.mean(signal)


def pre_emphasis(signal, alpha=PRE_EMPHASIS):
    """Filtru de pre-accentuare (trece-sus de ordinul 1):

        y[0] = x[0]
        y[n] = x[n] - alpha · x[n-1]

    Vocea are mai multă energie la frecvențe joase; filtrul „ridică”
    frecvențele înalte, ca formanții superiori și consoanele să conteze
    la fel de mult în trăsăturile spectrale (MFCC)."""
    emphasized = np.empty_like(signal)
    emphasized[0] = signal[0]
    emphasized[1:] = signal[1:] - alpha * signal[:-1]
    return emphasized


def normalize(signal):
    """Normalizare de amplitudine: cel mai mare vârf devine 0.95.
    Așa vocea are același nivel, indiferent cât de departe ești de microfon."""
    peak = np.max(np.abs(signal))
    if peak < 1e-6:  # semnal practic nul (liniște totală)
        return signal
    return signal / peak * 0.95


# ======================================================================
# 3. Analiza pe cadre scurte (short-time analysis)
# ======================================================================

def frame_signal(signal, frame_ms=FRAME_MS, hop_ms=HOP_MS, sample_rate=SAMPLE_RATE):
    """Împarte semnalul în cadre suprapuse.

    Vocea se schimbă continuu, dar pe 20–30 ms o putem considera
    „aproape staționară”, deci o analizăm bucată cu bucată.

    Întoarce o matrice cu forma (număr_cadre, lungime_cadru):
    rândul i = eșantioanele de la i·hop până la i·hop + frame_len."""
    frame_len = int(sample_rate * frame_ms / 1000)   # 400 eșantioane
    hop = int(sample_rate * hop_ms / 1000)            # 160 eșantioane

    # Dacă semnalul e mai scurt decât un cadru, îl completăm cu zerouri
    if len(signal) < frame_len:
        signal = np.pad(signal, (0, frame_len - len(signal)))

    num_frames = 1 + (len(signal) - frame_len) // hop
    frames = np.empty((num_frames, frame_len), dtype=np.float32)
    for i in range(num_frames):
        start = i * hop
        frames[i] = signal[start:start + frame_len]
    return frames


def short_time_energy(frames):
    """Energia pe termen scurt a fiecărui cadru (puterea medie):

        E = (1/N) · Σ x[n]²

    Vorbirea are energie mare, liniștea are energie mică."""
    return np.sum(frames ** 2, axis=1) / frames.shape[1]


def energy_to_db(energy):
    """Energie -> decibeli: 10·log10(E). 0 dB = semnal maxim (dBFS)."""
    return 10 * np.log10(energy + 1e-10)  # +1e-10 ca să nu calculăm log(0)


def zero_crossing_rate(frames):
    """Rata trecerilor prin zero a fiecărui cadru:

        ZCR = (1 / 2N) · Σ |sign(x[n]) - sign(x[n-1])|

    = fracția de eșantioane la care semnalul își schimbă semnul.
      - vocale (sonore, periodice):  ZCR mic  (~0.02–0.1)
      - consoane fricative (s, f, ș): ZCR mare (~0.3–0.5), dar energie mică
      - zgomot alb:                   ZCR mare"""
    signs = np.sign(frames)
    signs[signs == 0] = 1  # zero îl considerăm pozitiv
    crossings = np.abs(np.diff(signs, axis=1))   # 2 la fiecare schimbare de semn, altfel 0
    return np.sum(crossings, axis=1) / (2 * frames.shape[1])


# ======================================================================
# 4. VAD: detecția activității vocale
# ======================================================================

def detect_speech(signal, sample_rate=SAMPLE_RATE):
    """Găsește zona cu vorbire, folosind energia și ZCR.

    Regula pentru fiecare cadru (inspirată din algoritmul Rabiner–Sambur):
      - VORBIRE dacă energia > pragul de SUS  (sigur e voce: vocale, consoane sonore)
      - VORBIRE dacă energia > pragul de JOS  ȘI  ZCR > ZCR_THRESHOLD
                                              (voce slabă, dar „șuierată”: s, f, ș)
      - altfel LINIȘTE

    Pragurile se adaptează: pornesc de la nivelul zgomotului de fond,
    estimat din cele mai liniștite cadre.

    Apoi „netezim” decizia:
      - pauzele scurte (< 200 ms) dintre cuvinte devin vorbire;
      - zonele de vorbire foarte scurte (< 100 ms) devin liniște.

    Întoarce un dicționar cu toate valorile intermediare (utile pentru grafice):
      has_speech, start, end (în eșantioane), mask (per cadru),
      energy_db, zcr, noise_db, low_db, high_db
    """
    frames = frame_signal(signal, sample_rate=sample_rate)
    hop = int(sample_rate * HOP_MS / 1000)
    frame_len = frames.shape[1]

    energy_db = energy_to_db(short_time_energy(frames))
    zcr = zero_crossing_rate(frames)

    # Pragurile adaptive
    noise_db = np.percentile(energy_db, NOISE_PERCENTILE)
    low_db = max(noise_db + LOW_MARGIN_DB, MIN_SPEECH_DB)
    high_db = max(noise_db + HIGH_MARGIN_DB, MIN_SPEECH_DB)

    # Decizia pe fiecare cadru
    loud = energy_db > high_db
    soft_fricative = (energy_db > low_db) & (zcr > ZCR_THRESHOLD)
    mask = loud | soft_fricative

    # Netezire
    mask = _fill_short_gaps(mask, max_len=MAX_GAP_MS // HOP_MS)
    mask = _remove_short_runs(mask, min_len=MIN_SPEECH_MS // HOP_MS)

    result = {
        "mask": mask,
        "energy_db": energy_db,
        "zcr": zcr,
        "noise_db": float(noise_db),
        "low_db": float(low_db),
        "high_db": float(high_db),
        "has_speech": bool(mask.any()),
        "start": 0,
        "end": 0,
    }

    if result["has_speech"]:
        speech_frames = np.flatnonzero(mask)
        margin = int(sample_rate * MARGIN_MS / 1000)
        start = speech_frames[0] * hop - margin
        end = speech_frames[-1] * hop + frame_len + margin
        result["start"] = int(max(0, start))
        result["end"] = int(min(len(signal), end))

    return result


def _runs(mask):
    """Găsește secvențele de valori egale: [(valoare, început, lungime), ...]"""
    runs = []
    start = 0
    for i in range(1, len(mask) + 1):
        if i == len(mask) or mask[i] != mask[start]:
            runs.append((bool(mask[start]), start, i - start))
            start = i
    return runs


def _fill_short_gaps(mask, max_len):
    """Pauzele (False) scurte, aflate ÎNTRE două zone de vorbire, devin vorbire."""
    mask = mask.copy()
    runs = _runs(mask)
    for k, (value, start, length) in enumerate(runs):
        is_inside = 0 < k < len(runs) - 1
        if not value and is_inside and length <= max_len:
            mask[start:start + length] = True
    return mask


def _remove_short_runs(mask, min_len):
    """Zonele de vorbire (True) prea scurte devin liniște."""
    mask = mask.copy()
    for value, start, length in _runs(mask):
        if value and length < min_len:
            mask[start:start + length] = False
    return mask


# ======================================================================
# 5. Tot lanțul
# ======================================================================

def preprocess(signal, use_vad=True):
    """Aplică lanțul complet de preprocesare.

    Întoarce (semnal_curat, vad):
      - semnal_curat: doar zona cu vorbire, normalizată (sau None dacă nu e vorbire)
      - vad: rezultatul lui detect_speech() (sau None dacă use_vad=False)

    use_vad=False păstrează tot semnalul (folosit în evaluare, ca să vedem
    cât contează VAD-ul)."""
    signal = remove_dc(signal)

    if not use_vad:
        return normalize(signal).astype(np.float32), None

    vad = detect_speech(signal)
    if not vad["has_speech"]:
        return None, vad

    trimmed = signal[vad["start"]:vad["end"]]
    return normalize(trimmed).astype(np.float32), vad
