"""
evaluate.py: compară cele două metode de recunoaștere, pentru documentație.

Date (înregistrate din pagina #/record):
    evaluation/data/quiet/<comanda>/*.wav    în liniște
    evaluation/data/noise/<comanda>/*.wav    cu zgomot de fond
    speech/templates_audio/<comanda>/*.wav   șabloanele pentru DTW

Fiecare fișier trece prin: metoda (Whisper / DTW) × preprocesare (cu / fără VAD).
Comanda găsită == numele folderului?  -> corect.

Rezultate în evaluation/results/:
    results.csv                      fiecare fișier: ce s-a recunoscut și în cât timp
    summary.md                       tabelul pentru documentație
    accuracy.png                     acuratețea pe metodă, condiție și preprocesare
    processing_time.png              timpul mediu pe metodă
    confusion_<metoda>_<cond>.png    matricea de confuzie

Rulare:
    docker compose exec speech python /evaluation/evaluate.py
    docker compose exec speech python /evaluation/evaluate.py --methods dtw     (doar DTW, rapid)
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, "/app")   # modulele din speech/ (în container sunt în /app)
import recognizer_dtw  # noqa: E402
import recognizer_whisper  # noqa: E402
from commands import COMMANDS, interpret  # noqa: E402
from preprocessing import load_wav_file, preprocess  # noqa: E402

HERE = Path(__file__).parent
CONDITIONS = ["quiet", "noise"]
COLORS = {"whisper": "#2a78d6", "dtw": "#eb6834"}
NAMES = {"whisper": "Whisper", "dtw": "MFCC + DTW"}


def recognize(path, method, use_vad):
    """Un fișier -> (comanda recunoscută, timpul în ms)."""
    start = time.perf_counter()
    clean = preprocess(load_wav_file(path), use_vad)
    if clean is None:
        action = "unknown"
    elif method == "whisper":
        action = interpret(recognizer_whisper.transcribe(clean)[0])["action"]
    else:
        action = recognizer_dtw.recognize(clean)["action"]
    return action, (time.perf_counter() - start) * 1000


def plot_accuracy(rows, methods, out):
    """Bare grupate. Fără preprocesare = bară hașurată, de aceeași culoare."""
    conditions = [c for c in CONDITIONS if any(r["condition"] == c for r in rows)]   # doar cele cu date
    groups = [(m, vad) for m in methods for vad in (True, False)]
    width = 0.8 / len(groups)
    fig, ax = plt.subplots(figsize=(8, 4.5))

    for k, (method, vad) in enumerate(groups):
        accuracies = [accuracy(rows, method, c, vad) for c in conditions]
        x = np.arange(len(conditions)) - 0.4 + width * (k + 0.5)
        bars = ax.bar(x, accuracies, width * 0.95, edgecolor=COLORS[method], linewidth=1.5,
                      color=COLORS[method] if vad else "white", hatch=None if vad else "///",
                      label=f"{NAMES[method]}, {'with' if vad else 'without'} preprocessing")
        ax.bar_label(bars, fmt="%.0f%%", fontsize=9)

    ax.set_xticks(range(len(conditions)), [{"quiet": "Quiet room", "noise": "Background noise"}[c] for c in conditions])
    ax.set_ylim(0, 110)
    ax.set_ylabel("accuracy (%)")
    ax.set_title("Command recognition accuracy", loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
    fig.tight_layout()
    fig.savefig(out / "accuracy.png", dpi=150)


def plot_time(rows, methods, out):
    times = [[r["ms"] for r in rows if r["method"] == m and r["vad"]] for m in methods]
    fig, ax = plt.subplots(figsize=(6, 3.8))
    bars = ax.bar([NAMES[m] for m in methods], [np.mean(t) for t in times], width=0.5,
                  yerr=[np.std(t) for t in times], capsize=6, color=[COLORS[m] for m in methods])
    ax.bar_label(bars, fmt="%.0f ms", padding=4)
    ax.set_ylabel("ms per command")
    ax.set_title("Average processing time (with preprocessing)", loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "processing_time.png", dpi=150)


def plot_confusion(rows, method, condition, out):
    """Rândul = comanda spusă, coloana = comanda recunoscută. Diagonala = corect."""
    selected = [r for r in rows if r["method"] == method and r["condition"] == condition and r["vad"]]
    if not selected:
        return
    labels = [a for a in COMMANDS if any(r["label"] == a for r in selected)]
    columns = labels + ["unknown"]
    matrix = np.zeros((len(labels), len(columns)))
    for r in selected:
        column = r["predicted"] if r["predicted"] in columns else "unknown"
        matrix[labels.index(r["label"]), columns.index(column)] += 1
    percent = matrix / matrix.sum(axis=1, keepdims=True) * 100

    fig, ax = plt.subplots(figsize=(1 + 0.6 * len(columns), 1 + 0.5 * len(labels)))
    ax.imshow(percent, cmap="Blues", vmin=0, vmax=100)
    for i, j in zip(*np.nonzero(matrix)):
        ax.text(j, i, f"{percent[i, j]:.0f}", ha="center", va="center", fontsize=8,
                color="white" if percent[i, j] > 55 else "black")
    ax.set_xticks(range(len(columns)), columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    ax.set_xlabel("recognized as")
    ax.set_ylabel("spoken command")
    ax.set_title(f"Confusion matrix (%): {NAMES[method]}, {condition}", loc="left", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / f"confusion_{method}_{condition}.png", dpi=150)


def accuracy(rows, method, condition, vad):
    group = [r["predicted"] == r["label"] for r in rows
             if r["method"] == method and r["condition"] == condition and r["vad"] == vad]
    return 100 * np.mean(group) if group else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=HERE / "data")
    parser.add_argument("--templates", type=Path, default=recognizer_dtw.TEMPLATES_DIR)
    parser.add_argument("--out", type=Path, default=HERE / "results")
    parser.add_argument("--methods", default="whisper,dtw")
    args = parser.parse_args()
    methods = args.methods.split(",")

    files = sorted(args.data.glob("*/*/*.wav"))   # data/<condiție>/<comandă>/fișier.wav
    if not files:
        return print(f"No test recordings in {args.data}. Record them at #/record (Test set).")

    if "dtw" in methods:
        recognizer_dtw.TEMPLATES_DIR = args.templates
        recognizer_dtw.load_templates()
        if not recognizer_dtw.templates:
            print("No DTW templates: skipping DTW.")
            methods.remove("dtw")
    if "whisper" in methods:
        recognizer_whisper.load_model()

    rows = []
    for method in methods:
        for vad in (True, False):
            for path in files:
                predicted, ms = recognize(path, method, vad)
                rows.append({"file": path.name, "condition": path.parent.parent.name, "label": path.parent.name,
                             "method": method, "vad": vad, "predicted": predicted, "ms": round(ms, 1)})
            print(f"  {NAMES[method]:<11} VAD {'on ' if vad else 'off'}: done")

    out = args.out
    out.mkdir(exist_ok=True)
    with open(out / "results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    table = ["| Method | Condition | Preprocessing | Accuracy | Mean time |", "|---|---|---|---|---|"]
    for method in methods:
        for condition in CONDITIONS:
            for vad in (True, False):
                times = [r["ms"] for r in rows if r["method"] == method and r["condition"] == condition and r["vad"] == vad]
                if times:
                    table.append(f"| {NAMES[method]} | {condition} | {'on' if vad else 'off'} | "
                                 f"{accuracy(rows, method, condition, vad):.1f}% | {np.mean(times):.0f} ms |")
    (out / "summary.md").write_text("\n".join(table) + "\n")

    plot_accuracy(rows, methods, out)
    plot_time(rows, methods, out)
    for method in methods:
        for condition in CONDITIONS:
            plot_confusion(rows, method, condition, out)

    print("\n" + "\n".join(table) + f"\n\nResults saved in {out}")


if __name__ == "__main__":
    main()
