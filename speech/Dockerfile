# Serviciul de prelucrare a vocii: Python 3.11
FROM python:3.11-slim

WORKDIR /app

# Dependențele (faster-whisper aduce cu el și decodorul audio,
# deci NU avem nevoie de ffmpeg)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fără --debug: în modul debug Flask pornește procesul de două ori
# și ar încărca modelul Whisper de două ori.
# După ce modifici codul: docker compose restart speech
CMD ["flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5001"]
