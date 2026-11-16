---
tags: [utter-butter, docker]
---

# 02 Docker Compose

Înapoi la [[00 Start aici]] · vezi și [[01 Arhitectura generală]]

## Ce e Docker, pe scurt
- **Imagine** = „rețeta” unui calculator mic: sistem de operare + Python + bibliotecile noastre. Se descrie într-un `Dockerfile`.
- **Container** = o imagine pornită, care rulează izolat.
- **Docker Compose** = pornește mai multe containere deodată, din fișierul `docker-compose.yml`, și le pune într-o rețea comună. În rețeaua asta, containerele se găsesc unul pe altul **după nume** (`api`, `db`, `speech`).

## Serviciile din `docker-compose.yml`

| Serviciu | Imagine | Port | Volume (foldere legate) |
|---|---|---|---|
| `db` | `postgres:16-alpine` (gata făcută) | 5432, doar intern | `db-data` (datele), `db/init.sql` |
| `api` | construită din `api/Dockerfile` | 5000, doar intern | `./api` → `/app` |
| `speech` | construită din `speech/Dockerfile` | 5001, doar intern | `./speech` → `/app`, `./evaluation` → `/evaluation`, `whisper-models` |
| `web` | construită din `web/Dockerfile` (nginx) | **8090 → 80**, singurul port deschis spre Windows | `./web/public`, `./web/nginx.conf` |

Doar `web` e accesibil din browser. Celelalte servicii sunt „în spatele” lui nginx, vezi [[03 Frontend web#nginx]].

## Lucruri importante din fișier
- `name: utterbutter` e numele proiectului. Folderul conține `&`, pe care Docker nu îl acceptă.
- **`depends_on` + `healthcheck`:** `api` pornește doar după ce Postgres răspunde (`pg_isready`).
- **Volume cu cod** (`./api:/app`): codul de pe Windows e „văzut” direct în container, deci o modificare nu cere rebuild.
  - `api` are Flask în mod `--debug` și repornește singur.
  - `speech` **nu** e în debug (ar încărca Whisper de două ori), așa că după modificări rulezi `docker compose restart speech`.
- **Volume cu nume:**
  - `db-data`: rețetele rămân salvate după oprire
  - `whisper-models`: modelul Whisper (~150 MB) se descarcă o singură dată
- **Variabile de mediu** pentru `speech`:
  - `WHISPER_MODEL=base`
  - `SAVE_RECORDINGS_DIR`: salvează fiecare comandă primită
  - `DATASET_DIR`: setul de test pentru evaluare
  - `MPLBACKEND=Agg`: graficele se desenează direct în PNG, fără fereastră

## Dockerfile-urile Python (`api`, `speech`)
```dockerfile
FROM python:3.11-slim            # imaginea de bază
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt   # pas separat → păstrat în cache
COPY . .
CMD ["flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5000"]
```
`--host 0.0.0.0` = serverul acceptă conexiuni din celelalte containere, nu doar din el însuși.

## Comenzi
Vezi [[13 Rulare și depanare]].
