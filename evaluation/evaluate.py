"""
evaluate.py: evaluarea celor două metode de recunoaștere, pentru documentație.

Datele (înregistrate din pagina #/record a aplicației):
    evaluation/data/quiet/<comanda>/*.wav     în liniște
    evaluation/data/noise/<comanda>/*.wav     cu zgomot de fond (hotă, apă, muzică)
    speech/templates_audio/<comanda>/*.wav    șabloanele pentru MFCC + DTW

Pentru fiecare fișier și fiecare combinație
    metodă (Whisper / DTW) × preprocesare (cu / fără VAD)
se rulează recunoașterea și se compară comanda găsită cu eticheta (numele folderului).

Rezultate în evaluation/results/:
    results.csv                    fiecare fișier, cu predicția și timpul
    summary.csv / summary.md       acuratețea și timpul mediu, pe grupe
    accuracy.png                   acuratețea: metodă × condiție × preprocesare
    processing_time.png            timpul mediu de procesare pe metodă
    confusion_<metoda>_<cond>.png  matricea de confuzie (cu preprocesare)

Rulare (cu containerele pornite):
    docker compose exec speech python /evaluation/evaluate.py
    docker compose exec speech python /evaluation/evaluate.py --methods dtw   (doar DTW, rapid)
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Modulele noastre de prelucrare sunt în folderul speech/ (în container: /app)
HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent / "speech", Path("/app")):
    if (candidate / "preprocessing.py").exists():
        sys.path.insert(0, str(candidate))
        SPEECH_DIR = candidate
        break

import recognizer_dtw  # noqa: E402
import recognizer_whisper  # noqa: E402
from commands import COMMANDS, interpret  # noqa: E402
from preprocessing import load_wav_file, preprocess  # noqa: E402

CONDITIONS = ("quiet", "noise")
ACTIONS = list(COMMANDS)          # ordinea comenzilor în tabele și grafice
EXPECTED_TIMER_VALUE = 5          # în setul de test spunem „start timer five minutes”

# Culori (paletă categorială testată pentru daltonism) și cerneală pentru text
COLORS = {"whisper": "#2a78d6", "dtw": "#eb6834"}
INK, INK_MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
METHOD_NAMES = {"whisper": "Whisper", "dtw": "MFCC + DTW"}


# ======================================================================
# Recunoașterea unui fișier
# ======================================================================

def recognize_file(path, method, use_vad):
    """Rulează lanțul complet pe un fișier. Întoarce (acțiune, valoare, text, ms)."""
    start = time.perf_counter()
    clean, _ = preprocess(load_wav_file(path), use_vad=use_vad)

    if clean is None:                      # VAD: nu e vorbire
        action, value, text = "unknown", None, ""
    elif method == "whisper":
        text, _ = recognizer_whisper.transcribe(clean)
        result = interpret(text)
        action, value = result["action"], result["value"]
    else:
        result = recognizer_dtw.recognize(clean)
        action, value, text = result["action"], None, f"d={result['distance']}"

    elapsed_ms = (time.perf_counter() - start) * 1000
    return action, value, text, elapsed_ms


def collect_files(data_dir):
    """[(condiție, eticheta, cale), ...] pentru toate fișierele din setul de test."""
    files = []
    for condition in CONDITIONS:
        for action in ACTIONS:
            folder = data_dir / condition / action
            if folder.exists():
                files += [(condition, action, p) for p in sorted(folder.glob("*.wav"))]
    return files


# ======================================================================
# Grafice
# ======================================================================

def style_axes(ax):
    """Axe discrete: fără chenar sus/dreapta, grilă fină doar pe orizontală."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_MUTED)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def plot_accuracy(summary, methods, out_dir):
    """Bare grupate: pe axa x condiția, în fiecare grup metoda × preprocesare.
    Fără preprocesare = aceeași culoare, cu hașuri (nu doar culoarea diferă)."""
    groups = [(m, vad) for m in methods for vad in (True, False)]
    width = 0.8 / len(groups)
    x = np.arange(len(CONDITIONS))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for k, (method, vad) in enumerate(groups):
        values = [summary.get((method, c, vad), {}).get("accuracy", np.nan) * 100 for c in CONDITIONS]
        positions = x - 0.4 + width * (k + 0.5)
        bars = ax.bar(
            positions, values, width=width - 0.02,
            color=COLORS[method] if vad else "white",
            edgecolor=COLORS[method], linewidth=1.5,
            hatch=None if vad else "///",
            label=f"{METHOD_NAMES[method]}, {'with' if vad else 'without'} preprocessing",
        )
        for bar, value in zip(bars, values):
            if not np.isnan(value):
                ax.text(bar.get_x() + bar.get_width() / 2, value + 1.5, f"{value:.0f}%",
                        ha="center", va="bottom", fontsize=9, color=INK)

    ax.set_xticks(x, ["Quiet room", "Background noise"], color=INK)
    ax.set_ylim(0, 110)
    ax.set_ylabel("accuracy (%)", color=INK_MUTED)
    ax.set_title("Command recognition accuracy", color=INK, loc="left", fontsize=13)
    style_axes(ax)
    ax.legend(frameon=False, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    fig.tight_layout()
    fig.savefig(out_dir / "accuracy.png", dpi=150)
    plt.close(fig)


def plot_time(rows, methods, out_dir):
    """Timpul mediu de procesare pe metodă (cu preprocesare), cu deviația standard."""
    fig, ax = plt.subplots(figsize=(6, 3.8))
    means, stds = [], []
    for method in methods:
        times = [r["ms"] for r in rows if r["method"] == method and r["preprocess"]]
        means.append(np.mean(times) if times else 0)
        stds.append(np.std(times) if times else 0)

    names = [METHOD_NAMES[m] for m in methods]
    bars = ax.bar(names, means, yerr=stds, width=0.5, capsize=6,
                  color=[COLORS[m] for m in methods], error_kw={"ecolor": INK_MUTED, "lw": 1})
    tallest = max(means) or 1
    for bar, mean, std in zip(bars, means, stds):
        x = bar.get_x() + bar.get_width() / 2
        if mean > 0.2 * tallest:   # bară înaltă: eticheta în interior
            ax.text(x, mean / 2, f"{mean:.0f} ms", ha="center", va="center",
                    color="white", fontsize=11, fontweight="bold")
        else:                      # bară scurtă: eticheta deasupra
            ax.text(x, mean + std + 0.03 * tallest, f"{mean:.0f} ms", ha="center",
                    va="bottom", color=INK, fontsize=11, fontweight="bold")
    ax.set_ylabel("processing time per command (ms)", color=INK_MUTED)
    ax.set_title("Average processing time (with preprocessing)", color=INK, loc="left", fontsize=13)
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(out_dir / "processing_time.png", dpi=150)
    plt.close(fig)


def plot_confusion(rows, method, condition, out_dir):
    """Matricea de confuzie: rândul = comanda spusă, coloana = comanda recunoscută.
    Pe diagonală = corect. Valorile sunt procente din fiecare rând."""
    selected = [r for r in rows if r["method"] == method and r["condition"] == condition and r["preprocess"]]
    if not selected:
        return
    labels = [a for a in ACTIONS if any(r["label"] == a for r in selected)]
    columns = labels + ["unknown"]
    matrix = np.zeros((len(labels), len(columns)))
    for r in selected:
        predicted = r["predicted"] if r["predicted"] in columns else "unknown"
        matrix[labels.index(r["label"]), columns.index(predicted)] += 1
    percent = matrix / matrix.sum(axis=1, keepdims=True) * 100

    # Scală secvențială: o singură nuanță, de la deschis la închis
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", ["#fcfcfb", "#9ec5f4", "#2a78d6", "#104281"])

    fig, ax = plt.subplots(figsize=(1 + 0.62 * len(columns), 1 + 0.55 * len(labels)))
    ax.imshow(percent, cmap=cmap, vmin=0, vmax=100)
    for i in range(len(labels)):
        for j in range(len(columns)):
            if matrix[i, j] > 0:
                ax.text(j, i, f"{percent[i, j]:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if percent[i, j] > 55 else INK)
    ax.set_xticks(range(len(columns)), columns, rotation=45, ha="right", fontsize=8, color=INK)
    ax.set_yticks(range(len(labels)), labels, fontsize=8, color=INK)
    ax.set_xlabel("recognized as", color=INK_MUTED)
    ax.set_ylabel("spoken command", color=INK_MUTED)
    ax.set_title(f"Confusion matrix (%): {METHOD_NAMES[method]}, {condition}", color=INK, loc="left", fontsize=11)
    for side in ax.spines.values():
        side.set_visible(False)
    fig.tight_layout()
    fig.savefig(out_dir / f"confusion_{method}_{condition}.png", dpi=150)
    plt.close(fig)


# ======================================================================
# Programul principal
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description="Evaluate Whisper vs MFCC + DTW")
    parser.add_argument("--data", type=Path, default=HERE / "data")
    parser.add_argument("--templates", type=Path, default=SPEECH_DIR / "templates_audio")
    parser.add_argument("--out", type=Path, default=HERE / "results")
    parser.add_argument("--methods", default="whisper,dtw")
    args = parser.parse_args()

    methods = [m for m in args.methods.split(",") if m in ("whisper", "dtw")]
    files = collect_files(args.data)
    if not files:
        print(f"No test recordings in {args.data}. Record them at http://localhost:8090/#/record (Test set).")
        return

    if "dtw" in methods:
        recognizer_dtw.TEMPLATES_DIR = args.templates
        recognizer_dtw.load_templates()
        if not recognizer_dtw.has_templates():
            print("No DTW templates: skipping DTW. Record them at #/record (Templates).")
            methods.remove("dtw")
    if "whisper" in methods:
        recognizer_whisper.load_model()

    print(f"{len(files)} test files, methods: {methods}\n")

    # Rularea propriu-zisă
    rows = []
    for method in methods:
        for use_vad in (True, False):
            for condition, label, path in files:
                predicted, value, text, ms = recognize_file(path, method, use_vad)
                rows.append({
                    "file": f"{condition}/{label}/{path.name}", "condition": condition,
                    "label": label, "method": method, "preprocess": use_vad,
                    "predicted": predicted, "value": value, "text": text, "ms": ms,
                    "correct": predicted == label,
                })
            done = [r for r in rows if r["method"] == method and r["preprocess"] == use_vad]
            accuracy = np.mean([r["correct"] for r in done]) * 100
            print(f"  {METHOD_NAMES[method]:<11} preprocessing={'on ' if use_vad else 'off'}  "
                  f"accuracy {accuracy:5.1f}%  ({len(done)} files)")

    args.out.mkdir(parents=True, exist_ok=True)

    # results.csv: tot
    with open(args.out / "results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        for r in rows:
            writer.writerow({**r, "ms": round(r["ms"], 1)})

    # Rezumatul pe grupe: (metodă, condiție, preprocesare)
    summary = {}
    for method in methods:
        for condition in CONDITIONS:
            for vad in (True, False):
                group = [r for r in rows if r["method"] == method
                         and r["condition"] == condition and r["preprocess"] == vad]
                if not group:
                    continue
                timers = [r for r in group if r["label"] == "timer" and r["predicted"] == "timer"]
                summary[(method, condition, vad)] = {
                    "files": len(group),
                    "accuracy": float(np.mean([r["correct"] for r in group])),
                    "mean_ms": float(np.mean([r["ms"] for r in group])),
                    "timer_value_ok": (sum(r["value"] == EXPECTED_TIMER_VALUE for r in timers)
                                       if method == "whisper" else None),
                    "timer_count": len(timers),
                }

    with open(args.out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["method", "condition", "preprocessing", "files", "accuracy_%", "mean_ms"])
        for (method, condition, vad), s in summary.items():
            writer.writerow([method, condition, "on" if vad else "off", s["files"],
                             round(s["accuracy"] * 100, 1), round(s["mean_ms"])])

    # summary.md: tabelul gata de copiat în documentație
    lines = ["| Method | Condition | Preprocessing | Files | Accuracy | Mean time |",
             "|---|---|---|---|---|---|"]
    for (method, condition, vad), s in summary.items():
        lines.append(f"| {METHOD_NAMES[method]} | {condition} | {'on' if vad else 'off'} | "
                     f"{s['files']} | {s['accuracy'] * 100:.1f}% | {s['mean_ms']:.0f} ms |")
    timer_notes = [f"- Whisper, {c}: timer value correct in {s['timer_value_ok']}/{s['timer_count']} "
                   f"recognized timer commands"
                   for (m, c, vad), s in summary.items() if m == "whisper" and vad and s["timer_count"]]
    if timer_notes:
        lines += ["", *timer_notes]
    (args.out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Graficele
    plot_accuracy(summary, methods, args.out)
    plot_time(rows, methods, args.out)
    for method in methods:
        for condition in CONDITIONS:
            plot_confusion(rows, method, condition, args.out)

    print("\n" + "\n".join(lines))
    print(f"\nResults saved in {args.out}")


if __name__ == "__main__":
    main()
