---
tags: [utter-butter, index]
---

# 🧈 Utter & Butter: hartă de notițe

Aplicație web de rețete controlată prin voce. Temă la **Interfețe Om-Mașină**.
Ideea centrală: arătăm lanțul complet

> **semnal vocal → prelucrare → text / trăsături → comandă → acțiune în interfață**

## Cum citești notițele
**Varianta foarte simplă, cu scheme:** [[14 Schema logică pe înțelesul tuturor]]

Varianta tehnică: începe cu [[01 Arhitectura generală]], apoi mergi pe bucăți:

| Bucata | Notița | Fișiere principale |
|---|---|---|
| Cum pornește totul | [[02 Docker Compose]] | `docker-compose.yml` |
| Interfața (SPA) | [[03 Frontend web]] | `web/public/*` |
| Microfonul din browser | [[04 Ascultarea continuă (listener)]] | `web/public/listener.js` |
| Ecranul de gătit | [[05 Modul de gătit]] | `web/public/cooking.js` |
| Rețetele + baza de date | [[06 Backend API și PostgreSQL]] | `api/app.py`, `db/init.sql` |
| Serverul de voce | [[07 Serviciul speech]] | `speech/app.py` |
| Prelucrarea semnalului | [[08 Preprocesare și VAD]] | `speech/preprocessing.py` |
| Metoda A | [[09 Whisper și interpretarea comenzilor]] | `speech/recognizer_whisper.py`, `speech/commands.py` |
| Metoda B | [[10 MFCC și DTW]] | `speech/features.py`, `speech/recognizer_dtw.py` |
| Înregistrarea vocii | [[11 Voice recorder]] | `web/public/recorder.js` |
| Teste și grafice | [[12 Evaluare și grafice]] | `evaluation/*.py` |
| Comenzi utile, probleme | [[13 Rulare și depanare]] | n/a |

## Legătura cu materia (pentru documentație)
- **Analiza pe cadre scurte**, energie, ZCR → [[08 Preprocesare și VAD]]
- **Spectrogramă, scala Mel, MFCC** → [[10 MFCC și DTW]]
- **Recunoaștere clasică (DTW)** vs **rețea neuronală (Whisper)** → [[09 Whisper și interpretarea comenzilor]], [[10 MFCC și DTW]], [[12 Evaluare și grafice]]
- **Interfață hands-free** (feedback, always listening, accesibilitate) → [[05 Modul de gătit]], [[04 Ascultarea continuă (listener)]]
