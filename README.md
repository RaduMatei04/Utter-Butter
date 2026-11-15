# Utter & Butter

A voice-controlled recipe app. Course project for Human-Computer Interfaces (IOM).

## Requirements
- Windows with **Docker Desktop** running

## Start
In PowerShell, from the project folder:

```powershell
docker compose up --build
```

Open **http://localhost:8090**.

## Useful commands
| Command | What it does |
|---|---|
| `docker compose up --build` | build and start all services |
| `docker compose down` | stop everything (data is kept) |
| `docker compose down -v` | stop and **delete the database** (it is re-created from `db/init.sql`) |
| `docker compose logs -f api` | follow the logs of one service |

## Services
| Service | What it is |
|---|---|
| `web` | nginx: serves the SPA and proxies `/api/...` |
| `api` | Flask: recipes API (PostgreSQL) |
| `db` | PostgreSQL 16 with 3 demo recipes |
| `speech` | Flask: voice processing + Whisper (`POST /api/command`) |

## Signal plots (for the documentation)
Every voice command is saved in `evaluation/recordings/`. To plot the waveform, energy, ZCR, VAD, spectrogram and MFCC of the latest one:

```powershell
docker compose exec speech python /evaluation/plot_signal.py
```

The image is saved in `evaluation/results/`.

## Recording your voice (MFCC + DTW templates, test set)
Open **http://localhost:8090/#/record** (link at the bottom of the Home page).
- **Templates:** for each command click *Record 5* and say the phrase 5 times. The DTW method uses them immediately.
- **Test set:** the same, in a quiet room and with background noise. Used by the evaluation script.

## Evaluation (Whisper vs MFCC + DTW)
After recording the templates and the test set (quiet + noise):

```powershell
docker compose exec speech python /evaluation/evaluate.py
```

It writes `results.csv`, `summary.md` (a table for the documentation), `accuracy.png`, `processing_time.png` and confusion matrices to `evaluation/results/`. Add `--methods dtw` for a quick DTW-only run.

To try the DTW method in cooking mode: **http://localhost:8090/?method=dtw#/cook/1**

## Notes
The first start downloads the Whisper `base` model (~150 MB) into a Docker volume.
After changing Python code in `speech/`, run `docker compose restart speech`.
