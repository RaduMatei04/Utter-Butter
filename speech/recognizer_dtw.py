"""
recognizer_dtw.py: recunoaștere clasică, MFCC + DTW (Dynamic Time Warping).

Ideea:
  - pentru fiecare comandă avem câteva înregistrări-model („șabloane”), în
    templates_audio/<comanda>/*.wav, spuse de utilizator;
  - din fiecare șablon extragem secvența de vectori MFCC (un vector / 10 ms);
  - o comandă nouă se compară cu TOATE șabloanele prin DTW;
  - câștigă comanda șablonului cel mai apropiat (1-nearest-neighbour);
  - dacă și cel mai apropiat șablon e prea departe, răspunsul e „unknown”.

De ce DTW și nu o simplă diferență între vectori?
  Aceeași comandă e spusă de fiecare dată cu altă viteză („neeext” vs „next”).
  DTW găsește cea mai bună „aliniere” în timp între cele două secvențe:
  poate întinde sau comprima timpul, ca sunetele asemănătoare să fie comparate între ele.

Avantaje:      nu are nevoie de rețea neuronală, e rapid, merge cu 3–5 exemple.
Dezavantaje:   recunoaște doar comenzile fixe pentru care există șabloane,
               depinde de vorbitor și nu poate extrage numere („timer 5 minutes”).
"""

import os
import threading
from pathlib import Path

import numba
import numpy as np

from features import mfcc
from preprocessing import SAMPLE_RATE, load_wav_file, preprocess

TEMPLATES_DIR = Path(os.environ.get("TEMPLATES_DIR", Path(__file__).parent / "templates_audio"))

# Pragul de respingere = REJECT_FACTOR × distanța tipică dintre două șabloane
# ale ACELEIAȘI comenzi (calculată automat din șabloanele tale).
REJECT_FACTOR = 1.5

# Comenzile sunt scurte; un segment mai lung de atât e conversație, nu comandă.
MAX_COMMAND_SECONDS = 2.5

_templates = []      # listă de (acțiune, nume_fișier, matrice_MFCC)
_threshold = None    # pragul de respingere (None = încă nu se poate calcula)
_lock = threading.Lock()


# ======================================================================
# Trăsături
# ======================================================================

def extract_features(clean_signal):
    """Semnal preprocesat -> matrice (număr_cadre, 13) cu vectori MFCC.

    CMVN (Cepstral Mean and Variance Normalization): din fiecare coeficient
    scădem media și împărțim la deviația standard, pe toată înregistrarea.
    Așa eliminăm diferențele „constante” (alt microfon, altă distanță,
    alt volum) și rămâne doar forma sunetelor."""
    features = mfcc(clean_signal).T                    # (cadre, 13)
    mean = features.mean(axis=0)
    std = features.std(axis=0) + 1e-10
    return ((features - mean) / std).astype(np.float64)


# ======================================================================
# DTW, scris explicit
# ======================================================================

@numba.njit(cache=True)
def dtw_distance(a, b):
    """Distanța DTW între două secvențe de vectori, a (n × 13) și b (m × 13).

    D[i, j] = costul celei mai bune alinieri între primele i cadre din `a`
              și primele j cadre din `b`:

        D[i, j] = d(a[i], b[j]) + min( D[i-1, j],      (a avansează, b „stă pe loc”)
                                       D[i, j-1],      (b avansează, a „stă pe loc”)
                                       D[i-1, j-1] )   (avansează amândouă)

    unde d = distanța euclidiană între doi vectori MFCC.
    Rezultatul se împarte la (n + m), ca să putem compara secvențe de lungimi diferite.

    @numba.njit compilează funcția în cod mașină la prima rulare
    (două bucle for în Python pur ar fi de ~100 de ori mai lente)."""
    n, m = a.shape[0], b.shape[0]
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diff = a[i - 1] - b[j - 1]
            cost = np.sqrt(np.sum(diff * diff))
            D[i, j] = cost + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return D[n, m] / (n + m)


# ======================================================================
# Șabloanele
# ======================================================================

def load_templates():
    """Citește toate șabloanele din templates_audio/<acțiune>/*.wav
    și recalculează pragul de respingere."""
    global _templates, _threshold
    templates = []
    if TEMPLATES_DIR.exists():
        for folder in sorted(TEMPLATES_DIR.iterdir()):
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.wav")):
                clean, _ = preprocess(load_wav_file(path))
                if clean is None:
                    print(f"[dtw] skipped {path.name}: no speech", flush=True)
                    continue
                templates.append((folder.name, path.name, extract_features(clean)))

    threshold = _compute_threshold(templates)
    with _lock:
        _templates = templates
        _threshold = threshold

    counts = template_counts()
    print(f"[dtw] {len(templates)} templates loaded {counts}, threshold={threshold}", flush=True)
    return counts


def _compute_threshold(templates):
    """Pentru fiecare șablon căutăm cel mai apropiat ALT șablon al aceleiași comenzi.
    Mediana acestor distanțe = „cât de diferit spui de obicei aceeași comandă”.
    Pragul = REJECT_FACTOR × mediana."""
    same_class = []
    for i, (action_i, _, feats_i) in enumerate(templates):
        distances = [
            dtw_distance(feats_i, feats_j)
            for j, (action_j, _, feats_j) in enumerate(templates)
            if j != i and action_j == action_i
        ]
        if distances:
            same_class.append(min(distances))
    if not same_class:
        return None  # prea puține șabloane: nu respingem nimic
    return float(REJECT_FACTOR * np.median(same_class))


def template_counts():
    counts = {}
    for action, _, _ in _templates:
        counts[action] = counts.get(action, 0) + 1
    return counts


def has_templates():
    return len(_templates) > 0


# ======================================================================
# Recunoașterea
# ======================================================================

def recognize(clean_signal):
    """Semnal preprocesat -> {"action", "distance", "threshold", "scores"}

    scores = cea mai mică distanță DTW pentru fiecare comandă
             (utile în documentație: cât de „sigur” e clasificatorul)."""
    with _lock:
        templates, threshold = _templates, _threshold

    if len(clean_signal) / SAMPLE_RATE > MAX_COMMAND_SECONDS:
        return {"action": "unknown", "distance": None, "threshold": threshold, "scores": {}}

    query = extract_features(clean_signal)

    scores = {}
    for action, _, feats in templates:
        distance = dtw_distance(query, feats)
        if action not in scores or distance < scores[action]:
            scores[action] = distance

    best_action = min(scores, key=scores.get)
    best_distance = scores[best_action]

    if threshold is not None and best_distance > threshold:
        best_action = "unknown"

    return {
        "action": best_action,
        "distance": round(float(best_distance), 3),
        "threshold": None if threshold is None else round(threshold, 3),
        "scores": {a: round(float(d), 3) for a, d in sorted(scores.items(), key=lambda x: x[1])},
    }
