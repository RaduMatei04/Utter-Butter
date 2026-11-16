"""
plot_signal.py: grafice pentru documentație, pentru o înregistrare WAV.

6 grafice, unul sub altul:
  1. forma de undă + zona găsită de VAD
  2. energia pe termen scurt + pragurile
  3. rata trecerilor prin zero (ZCR) + pragul
  4. semnalul după preprocesare (ce primește Whisper)
  5. spectrograma
  6. MFCC

Rulare (cu containerele pornite):
    docker compose exec speech python /evaluation/plot_signal.py              # ultima comandă spusă
    docker compose exec speech python /evaluation/plot_signal.py <fișier.wav>

Imaginile se salvează în evaluation/results/.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, "/app")   # modulele din speech/ (în container sunt în /app)
from features import mfcc, spectrogram  # noqa: E402
from preprocessing import HOP, SAMPLE_RATE, ZCR_THRESHOLD, detect_speech, load_wav_file, preprocess, remove_dc  # noqa: E402

HERE = Path(__file__).parent
RESULTS = HERE / "results"


def plot(path):
    signal = remove_dc(load_wav_file(path))
    vad = detect_speech(signal)
    clean = preprocess(signal)

    t = np.arange(len(signal)) / SAMPLE_RATE                  # timpul fiecărui eșantion
    frame_t = np.arange(len(vad["energy_db"])) * HOP / SAMPLE_RATE   # timpul fiecărui cadru

    fig, ax = plt.subplots(6, 1, figsize=(11, 15), constrained_layout=True)
    fig.suptitle(f"Signal analysis: {path.name}", fontsize=14)

    ax[0].plot(t, signal, color="#5A3E2B", linewidth=0.6)
    if vad["has_speech"]:
        ax[0].axvspan(vad["start"] / SAMPLE_RATE, vad["end"] / SAMPLE_RATE, color="#E8BF3E", alpha=0.3, label="speech (VAD)")
        ax[0].legend(loc="upper right")
    ax[0].set_title("1. Waveform (DC removed)")

    ax[1].plot(frame_t, vad["energy_db"], color="#5A3E2B", label="short-time energy")
    ax[1].axhline(vad["high_db"], color="#B5482F", linestyle="--", label=f"high threshold ({vad['high_db']:.0f} dB)")
    ax[1].axhline(vad["low_db"], color="#E8BF3E", linestyle="--", label=f"low threshold ({vad['low_db']:.0f} dB)")
    ax[1].axhline(vad["noise_db"], color="gray", linestyle=":", label=f"noise floor ({vad['noise_db']:.0f} dB)")
    ax[1].set_title("2. Short-time energy (25 ms frames, 10 ms hop)")
    ax[1].set_ylabel("dB")
    ax[1].legend(loc="upper right", fontsize=8)

    ax[2].plot(frame_t, vad["zcr"], color="#5A3E2B", label="ZCR")
    ax[2].axhline(ZCR_THRESHOLD, color="#B5482F", linestyle="--", label=f"threshold ({ZCR_THRESHOLD})")
    ax[2].set_title("3. Zero-crossing rate")
    ax[2].legend(loc="upper right", fontsize=8)

    for a in ax[:3]:
        a.set_xlim(0, t[-1])

    if clean is not None:
        ax[3].plot(np.arange(len(clean)) / SAMPLE_RATE, clean, color="#3C9A5F", linewidth=0.6)
    else:
        ax[3].text(0.5, 0.5, "No speech detected", ha="center", transform=ax[3].transAxes)
    ax[3].set_title("4. After preprocessing: trimmed + normalized (sent to Whisper)")

    source = clean if clean is not None else signal
    spec, freqs, times = spectrogram(source)
    image = ax[4].pcolormesh(times, freqs, spec, cmap="magma", vmin=spec.max() - 80)
    fig.colorbar(image, ax=ax[4], label="dB")
    ax[4].set_title("5. Spectrogram (Hamming window, 512-point FFT)")
    ax[4].set_ylabel("Hz")

    coefficients = mfcc(source)
    # Doar pentru afișare: fiecare rând normalizat, altfel coeficientul 0 acoperă tot
    shown = (coefficients - coefficients.mean(axis=1, keepdims=True)) / (coefficients.std(axis=1, keepdims=True) + 1e-10)
    image = ax[5].pcolormesh(np.arange(shown.shape[1]) * HOP / SAMPLE_RATE, np.arange(13), shown,
                             cmap="coolwarm", vmin=-3, vmax=3)
    fig.colorbar(image, ax=ax[5])
    ax[5].set_title("6. MFCC (13 coefficients, each row normalized for display)")
    ax[5].set_xlabel("time (s)")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{path.stem}_analysis.png"
    fig.savefig(out, dpi=120)
    print(f"{path.name}: {'speech' if vad['has_speech'] else 'NO speech'} -> {out}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        files = [Path(arg) for arg in sys.argv[1:]]
    else:
        files = sorted((HERE / "recordings").glob("*.wav"))[-1:]   # cea mai nouă înregistrare
    if not files:
        print("No recordings yet. Say a command in cooking mode first.")
    for path in files:
        plot(path)
