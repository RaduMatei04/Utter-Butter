"""
recognizer_dtw.py: metoda B, MFCC + DTW (fără rețea neuronală).

  - Pentru fiecare comandă avem câteva înregistrări-model („șabloane”):
    templates_audio/<comanda>/*.wav, spuse de utilizator.
  - O comandă nouă se compară prin DTW cu toate șabloanele.
  - Câștigă comanda celui mai apropiat șablon.
  - Dacă și cel mai apropiat e prea departe, răspunsul e „unknown”.
"""

import os
from collections import Counter
from pathlib import Path

import numba
import numpy as np

from features import mfcc
from preprocessing import SAMPLE_RATE, load_wav_file, preprocess

TEMPLATES_DIR = Path(os.environ.get("TEMPLATES_DIR", Path(__file__).parent / "templates_audio"))
REJECT_FACTOR = 1.5   # prag = 1.5 × distanța obișnuită dintre două șabloane ale aceleiași comenzi
MAX_SECONDS = 2.5     # comenzile sunt scurte; mai lung = conversație

templates = []        # listă de (comanda, MFCC)
threshold = None      # pragul de respingere (None = prea puține șabloane ca să-l calculăm)


def features_of(clean_signal):
    """MFCC + CMVN: fiecare coeficient adus la medie 0 și deviație 1.
    Așa nu mai contează volumul sau microfonul, doar forma sunetelor.
    Întoarce o matrice (număr_cadre, 13): un vector la fiecare 10 ms."""
    features = mfcc(clean_signal).T
    return (features - features.mean(axis=0)) / (features.std(axis=0) + 1e-10)


@numba.njit(cache=True)   # numba transformă funcția în cod mașină (de ~100 de ori mai rapid)
def dtw_distance(a, b):
    """Dynamic Time Warping: cea mai bună aliniere în timp între două secvențe.

    D[i, j] = d(a[i], b[j]) + min(D[i-1, j], D[i, j-1], D[i-1, j-1])

    Așa „next” spus repede și „neeext” spus rar se pot compara cadru cu cadru.
    Împărțim la n + m ca să putem compara secvențe de lungimi diferite."""
    n, m = len(a), len(b)
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = np.sqrt(np.sum((a[i - 1] - b[j - 1]) ** 2))   # distanța euclidiană
            D[i, j] = cost + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return D[n, m] / (n + m)


def load_templates():
    """Citește toate șabloanele și calculează pragul de respingere."""
    global templates, threshold
    templates = []
    for path in sorted(TEMPLATES_DIR.glob("*/*.wav")):
        clean = preprocess(load_wav_file(path))
        if clean is not None:
            templates.append((path.parent.name, features_of(clean)))

    # Pentru fiecare șablon: cât de departe e cel mai apropiat ALT șablon al aceleiași comenzi?
    closest = []
    for i, (action, feats) in enumerate(templates):
        others = [dtw_distance(feats, f) for j, (a, f) in enumerate(templates) if a == action and j != i]
        if others:
            closest.append(min(others))
    threshold = REJECT_FACTOR * float(np.median(closest)) if closest else None

    print(f"[dtw] {len(templates)} templates {template_counts()}, threshold={threshold}", flush=True)


def template_counts():
    return dict(Counter(action for action, _ in templates))


def recognize(clean_signal):
    """Semnal preprocesat -> {"action", "distance", "scores"}."""
    if len(clean_signal) / SAMPLE_RATE > MAX_SECONDS:
        return {"action": "unknown", "distance": None, "scores": {}}

    query = features_of(clean_signal)

    # scores[comanda] = distanța până la cel mai apropiat șablon al ei
    scores = {}
    for action, feats in templates:
        distance = dtw_distance(query, feats)
        scores[action] = min(distance, scores.get(action, np.inf))

    best = min(scores, key=scores.get)
    if threshold is not None and scores[best] > threshold:
        best = "unknown"

    return {
        "action": best,
        "distance": round(min(scores.values()), 3),
        "scores": {a: round(d, 3) for a, d in sorted(scores.items(), key=lambda x: x[1])},
    }
