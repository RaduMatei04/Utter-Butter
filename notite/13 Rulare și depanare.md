---
tags: [utter-butter, comenzi, depanare]
---

# 13 Rulare și depanare

Înapoi la [[00 Start aici]] · vezi și [[02 Docker Compose]]

## Pornire / oprire (PowerShell, din folderul proiectului)
Întâi pornește **Docker Desktop**.

| Comandă | Ce face |
|---|---|
| `docker compose up -d --build` | construiește și pornește tot, în fundal |
| `docker compose ps` | ce containere rulează |
| `docker compose logs -f speech` | urmărești logurile unui serviciu (aici apare fiecare comandă recunoscută) |
| `docker compose restart speech` | după ce modifici cod Python în `speech/` |
| `docker compose down` | oprește tot; rețetele rămân salvate |
| `docker compose down -v` | oprește și **șterge baza de date** (se recreează din `init.sql`) |

Aplicația se deschide la **http://localhost:8090** (în Chrome, pentru microfon).

## Adrese utile

| Adresă | Ce e |
|---|---|
| `http://localhost:8090/#/` | Home |
| `http://localhost:8090/#/cook/1` | modul de gătit (Pancakes) |
| `http://localhost:8090/?method=dtw#/cook/1` | modul de gătit cu MFCC + DTW |
| `http://localhost:8090/#/record` | [[11 Voice recorder]] |
| `http://localhost:8090/api/speech/health` | Whisper e gata? câte șabloane DTW există? |
| `http://localhost:8090/api/recipes` | rețetele, ca JSON |

## Probleme întâlnite și cauzele lor

| Simptom | Cauza | Rezolvare |
|---|---|---|
| Pe 8080 răspunde altceva („Embedthis-http”) | alt program de pe Windows („ApplicationWebServer”) a ocupat portul | aplicația e pe **8090** |
| `speech` cade cu `No module named 'requests'` | faster-whisper 1.1.1 folosește `requests`, dar nu o declară | adăugat în `speech/requirements.txt` |
| `web` nu pornește: `host not found in upstream "speech"` | nginx căuta serviciile la pornire | `resolver 127.0.0.11` + variabile în `nginx.conf` |
| „Speech model is still loading…” | Whisper se încarcă la pornire (câteva secunde; prima dată descarcă ~150 MB) | aștepți |
| „Mic blocked” | browserul n-a primit acces la microfon | permite microfonul pentru `localhost:8090` (iconița din bara de adrese) |
| „Click to start listening” | după refresh, browserul cere un click înainte de sunet | click pe indicatorul de microfon |
| Laptopul bipăie continuu | alarma timer-ului, rămasă într-un tab deschis | „stop timer”, tasta **S** sau închide tab-ul. Acum se oprește singură după 1 minut. |
| DTW: „No DTW templates yet” | nu sunt șabloane | înregistrează-le la [[11 Voice recorder]] |
| Push pe GitHub respins („non-fast-forward”) | repo-ul de pe GitHub avea propriul „Initial commit” cu un README | `git pull origin main --allow-unrelated-histories`, rezolvi conflictul din `README.md`, apoi `git push` |

## Unde se salvează lucrurile

| Folder | Ce | În git? |
|---|---|---|
| `evaluation/recordings/` | fiecare comandă vocală primită | nu |
| `evaluation/data/` | setul de test | da, dacă nu-l adaugi în `.gitignore` |
| `evaluation/results/` | graficele și CSV-urile | nu |
| `speech/templates_audio/` | șabloanele DTW | da |
| volumul `db-data` | baza de date | nu (e în Docker) |
| volumul `whisper-models` | modelul Whisper | nu (e în Docker) |
