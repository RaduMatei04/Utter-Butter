"""
plot_signal.py: grafice pentru documentație, pentru o înregistrare WAV.

Pentru fiecare fișier desenează 6 grafice, unul sub altul:
  1. forma de undă (semnalul brut) + zona detectată ca vorbire de VAD
  2. energia pe termen scurt (dB) + cele două praguri
  3. rata trecerilor prin zero (ZCR) + pragul
  4. semnalul după preprocesare (tăiat + normalizat)
  5. spectrograma (după pre-emphasis)
  6. coeficienții MFCC

Rulare (din folderul proiectului, cu containerele pornite):

    # ultima comandă vocală primită de aplicație:
    docker compose exec speech python /evaluation/plot_signal.py

    # un fișier anume (calea din container, /evaluation = folderul evaluation/):
    docker compose exec speech python /evaluation/plot_signal.py /evaluation/recordings/xxx_next.wav

Imaginile se salvează în evaluation/results/.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Modulele noastre de prelucrare sunt în folderul speech/
# (în container: /app; local: ../speech)
HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent / "speech", Path("/app")):
    if (candidate / "preprocessing.py").exists():
        sys.path.insert(0, str(candidate))
        break

from features import mfcc, spectrogram  # noqa: E402
from preprocessing import (  # noqa: E402
    HOP_MS, SAMPLE_RATE, ZCR_THRESHOLD,
    detect_speech, load_wav_file, pre_emphasis, preprocess, remove_dc,
)

RECORDINGS_DIR = HERE / "recordings"
RESULTS_DIR = HERE / "results"

# Culorile graficelor (în tonurile aplicației)
BROWN = "#5A3E2B"
BUTTER = "#E8BF3E"
RED = "#B5482F"
GREEN = "#3C9A5F"


def plot_file(path):
    raw = load_wav_file(path)
    signal = remove_dc(raw)
    vad = detect_speech(signal)
    clean, _ = preprocess(raw)

    t = np.arange(len(signal)) / SAMPLE_RATE                 # timpul fiecărui eșantion
    frame_t = np.arange(len(vad["energy_db"])) * HOP_MS / 1000  # timpul fiecărui cadru

    fig, axes = plt.subplots(6, 1, figsize=(11, 15), constrained_layout=True)
    fig.suptitle(f"Signal analysis: {path.name}", fontsize=14, color=BROWN)

    # 1. Forma de undă + zona cu vorbire
    ax = axes[0]
    ax.plot(t, signal, color=BROWN, linewidth=0.6)
    if vad["has_speech"]:
        ax.axvspan(vad["start"] / SAMPLE_RATE, vad["end"] / SAMPLE_RATE,
                   color=BUTTER, alpha=0.3, label="speech (VAD)")
        ax.legend(loc="upper right")
    ax.set_title("1. Raw waveform (DC removed)")
    ax.set_ylabel("amplitude")
    ax.set_xlim(0, t[-1])

    # 2. Energia pe termen scurt
    ax = axes[1]
    ax.plot(frame_t, vad["energy_db"], color=BROWN, label="short-time energy")
    ax.axhline(vad["high_db"], color=RED, linestyle="--", label=f"high threshold ({vad['high_db']:.0f} dB)")
    ax.axhline(vad["low_db"], color=BUTTER, linestyle="--", label=f"low threshold ({vad['low_db']:.0f} dB)")
    ax.axhline(vad["noise_db"], color="gray", linestyle=":", label=f"noise floor ({vad['noise_db']:.0f} dB)")
    ax.fill_between(frame_t, vad["energy_db"].min(), vad["energy_db"].max(),
                    where=vad["mask"], color=GREEN, alpha=0.12, label="speech frames")
    ax.set_title("2. Short-time energy, 25 ms frames, 10 ms hop")
    ax.set_ylabel("dB")
    ax.set_xlim(0, t[-1])
    ax.legend(loc="upper right", fontsize=8)

    # 3. Zero-crossing rate
    ax = axes[2]
    ax.plot(frame_t, vad["zcr"], color=BROWN, label="ZCR")
    ax.axhline(ZCR_THRESHOLD, color=RED, linestyle="--", label=f"ZCR threshold ({ZCR_THRESHOLD})")
    ax.set_title("3. Zero-crossing rate")
    ax.set_ylabel("crossings / sample")
    ax.set_xlim(0, t[-1])
    ax.legend(loc="upper right", fontsize=8)

    # 4. Semnalul după preprocesare
    ax = axes[3]
    if clean is not None:
        ax.plot(np.arange(len(clean)) / SAMPLE_RATE, clean, color=GREEN, linewidth=0.6)
        ax.set_xlim(0, len(clean) / SAMPLE_RATE)
    else:
        ax.text(0.5, 0.5, "No speech detected", ha="center", va="center", transform=ax.transAxes)
    ax.set_title("4. After preprocessing: trimmed to speech + normalized (sent to Whisper)")
    ax.set_ylabel("amplitude")

    # 5. Spectrograma
    ax = axes[4]
    source = clean if clean is not None else signal
    spec_db, freqs, times = spectrogram(pre_emphasis(source))
    image = ax.pcolormesh(times, freqs, spec_db, shading="auto", cmap="magma",
                          vmin=spec_db.max() - 80, vmax=spec_db.max())
    fig.colorbar(image, ax=ax, label="dB")
    ax.set_title("5. Spectrogram (pre-emphasis, Hamming window, 512-point FFT)")
    ax.set_ylabel("frequency (Hz)")

    # 6. MFCC
    ax = axes[5]
    coefficients = mfcc(source)
    # Doar pentru afișare: fiecare coeficient e normalizat separat (medie 0, deviație 1).
    # Altfel coeficientul 0 (≈ energia) are valori mult mai mari și „acoperă” restul culorilor.
    mean = coefficients.mean(axis=1, keepdims=True)
    std = coefficients.std(axis=1, keepdims=True) + 1e-10
    shown = (coefficients - mean) / std
    mfcc_times = np.arange(coefficients.shape[1]) * HOP_MS / 1000
    image = ax.pcolormesh(mfcc_times, np.arange(coefficients.shape[0]), shown,
                          shading="nearest", cmap="coolwarm", vmin=-3, vmax=3)
    fig.colorbar(image, ax=ax, label="normalized")
    ax.set_yticks(range(coefficients.shape[0]))
    ax.set_title("6. MFCC (13 coefficients, 40 Mel filters; each row normalized for display)")
    ax.set_ylabel("coefficient")
    ax.set_xlabel("time (s)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{path.stem}_analysis.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)

    status = "speech" if vad["has_speech"] else "NO speech"
    print(f"{path.name}: {status}, saved {out}")


def main():
    if len(sys.argv) > 1:
        files = [Path(arg) for arg in sys.argv[1:]]
    else:
        # fără argumente: cea mai nouă înregistrare
        recordings = sorted(RECORDINGS_DIR.glob("*.wav"))
        if not recordings:
            print(f"No recordings in {RECORDINGS_DIR}. Say a command in cooking mode first.")
            return
        files = [recordings[-1]]

    for path in files:
        plot_file(path)


if __name__ == "__main__":
    main()
