# Utter & Butter — rezumat proiect pentru Claude Code

## 1. Context
- **Ce este:** temă de curs la materia **Interfețe Om-Mașină (IOM)**, anul 4, Electronică.
- **Titlul temei:** *„Interfețe hands-free: comenzi vocale pentru aplicații web — studiu de caz: Utter & Butter”*
- **Aplicația:** **Utter & Butter**, un site de rețete controlat prin voce. Scenariul: gătești, ai mâinile ocupate și navighezi prin rețetă vorbind („next step”, „repeat”, „start timer 5 minutes”).
- **Legătura cu materia:** la curs s-au studiat analiza semnalului vocal, fonemele și prelucrarea vocii în Python. Proiectul trebuie să arate clar **lanțul complet: semnal vocal → prelucrare → text → comandă → acțiune în interfață**.
- **Autor:** student cu nivel de programare **începător**. Codul trebuie să fie simplu, bine comentat și explicat pas cu pas.

## 2. Livrabile și termene
| Ce | Termen |
|---|---|
| Alegerea temei în fișierul de pe Moodle | 1 dec 2026 |
| Aplicația funcțională | ~ 22 nov 2026 |
| Teste + documentație (5 pagini, Word/PDF) | 1–7 dec 2026 |
| Slide-uri (4–6) + înregistrarea prezentării (5 min) | 8–12 dec 2026 |
| **Predare finală** | **12 dec 2026, 23:59** |

Aplicația e demo-ul din înregistrare. Demo-ul se face **local**, nu se publică online. Graficele (spectrograme, rezultatele testelor) sunt generate **doar în Python** și ajung în documentație și pe slide-uri, **nu** în interfața aplicației.

## 3. Arhitectură: servicii separate în Docker Desktop

Totul rulează cu `docker compose up`, cu patru servicii:

```
                 Browser (SPA)  →  http://localhost:8090
                        │
               ┌────────▼────────┐
               │  web (nginx)    │  servește SPA-ul (HTML/CSS/JS)
               │                 │  și redirecționează /api/...
               └───┬─────────┬───┘
     /api/recipes  │         │  /api/command
          ┌────────▼───┐ ┌───▼──────────────────────┐
          │ api (Flask)│ │ speech (Flask, Python)   │
          │ CRUD rețete│ │ preprocesare, MFCC,      │
          └─────┬──────┘ │ Whisper / DTW, comenzi   │
                │        └──────────────────────────┘
          ┌─────▼──────┐
          │ db         │  PostgreSQL + volum persistent
          │ (Postgres) │
          └────────────┘
```

| Serviciu | Rol | Port intern |
|---|---|---|
| `web` | nginx: fișierele statice ale SPA-ului + reverse proxy către `api` și `speech` | 80 (expus ca **8090**) |
| `api` | Flask: CRUD pentru rețete (`/api/recipes`) | 5000 |
| `speech` | Flask: `POST /api/command` primește WAV, face prelucrarea și întoarce comanda | 5001 |
| `db` | PostgreSQL 16, cu un volum pentru date și `init.sql` cu 2–3 rețete demo | 5432 |

- Microfonul merge pe `http://localhost` fără HTTPS.
- Modelul Whisper se descarcă o singură dată într-un volum Docker (cache).
- În dezvoltare, codul se montează ca volum ca să nu fie nevoie de rebuild la fiecare modificare.

**Decizie importantă:** prelucrarea și recunoașterea vorbirii se fac **în Python, nu cu Web Speech API** (`SpeechRecognition` din browser). În browser se folosește doar `speechSynthesis`, pentru citirea pasului la comanda „read”.

## 4. Tehnologii

### Frontend (serviciul `web`)
- **SPA în HTML + CSS + JavaScript simplu** (fără framework, fără build step), cu rutare pe hash:
  - `#/`: Home, cu rețetele utilizatorului
  - `#/new` și `#/edit/:id`: formular pentru adăugarea și editarea unei rețete
  - `#/cook/:id`: modul de gătit, cu microfonul pornit
  - `#/record`: unealtă de înregistrare (șabloane DTW + set de test), cu un link discret în josul paginii Home. Înlocuiește `record_dataset.py`, pentru că microfonul Windows nu e accesibil din Docker.
- **Web Audio API** pentru ascultare continuă (vezi §5.0)
- Fiecare segment de vorbire se trimite ca **WAV mono, 16 kHz, 16-bit PCM**, cu `fetch()` + `FormData`
- `window.speechSynthesis` doar pentru comanda „read”

### Backend
- **Python 3.11** în containere
- **Flask** în `api` și `speech`
- **psycopg** (v3) cu SQL scris de mână în `api` (fără ORM, ca să fie ușor de explicat)
- **faster-whisper**: speech-to-text local, model `base` sau `small`, în engleză și română
- **librosa**: MFCC, `librosa.sequence.dtw`
- **numpy / scipy**: calcule, filtre
- **matplotlib**: spectrograme și grafice pentru documentație (PNG, generate de scripturi Python)
- **difflib**: potrivire aproximativă a comenzilor

### Mediu
- Windows + **Docker Desktop**. Fiecare serviciu Python are propriul `Dockerfile` și `requirements.txt`.
- Scripturile de grafice și evaluare rulează **în containerul `speech`** (au deja numpy, librosa, matplotlib): `docker compose exec speech python /evaluation/plot_signal.py`. Folderul `evaluation/` e montat la `/evaluation`.
- Fiecare comandă primită de `speech` se salvează în `evaluation/recordings/<data>_<actiune>.wav` (variabila `SAVE_RECORDINGS_DIR`). Folderul e în `.gitignore`.

## 5. Lanțul de prelucrare

### 5.0 Ascultare continuă (în browser)
- În modul de gătit, microfonul e **mereu pornit** („always listening”), fără wake word.
- Browserul face doar o **segmentare grosieră**: un prag simplu de energie pe cadre detectează începutul vorbirii. Se păstrează ~300 ms dinainte (pre-roll), iar segmentul se închide după ~700 ms de liniște sau la maximum 5 s. Segmentul se trimite la `speech`.
- Cât timp aplicația vorbește (`speechSynthesis`), ascultarea e pusă pe **pauză**, ca să nu se audă singură.
- VAD-ul „adevărat” și toată prelucrarea se fac în Python.

### 5.1 Serviciul `speech`
1. **Încărcare:** WAV 16 kHz mono → `numpy` array normalizat în [-1, 1].
2. **Preprocesare (scrisă de noi, explicată în documentație):**
   - eliminarea componentei DC
   - **VAD (energie + ZCR):** pe cadre de 25 ms cu pas de 10 ms se calculează **energia pe termen scurt** (dB) și **zero-crossing rate**. Pragurile sunt adaptive: zgomotul de fond e percentila 10 a energiei, pragul de jos e zgomot + 6 dB, iar cel de sus zgomot + 12 dB.
     - Un cadru e vorbire dacă energia > pragul de sus, SAU energia > pragul de jos și ZCR > 0.25 (consoane fricative).
     - E vorbire doar dacă există cel puțin 10 cadre de vorbire (100 ms). Așa se resping clicurile.
     - Se taie liniștea, cu o margine de 150 ms. Cu 50 ms, în zgomot, VAD-ul tăia finalul cuvintelor slabe, iar Whisper scădea de la 87% la 80% pe setul sintetic. Dacă nu rămâne vorbire, Whisper nu mai rulează și răspunsul e `unknown`.
   - normalizarea amplitudinii (vârf 0.95)
   - **pre-emphasis** (`y[n] = x[n] - 0.97·x[n-1]`) se aplică **doar pe ramura MFCC/DTW** și în spectrogramă, nu înainte de Whisper. Whisper a fost antrenat pe vorbire naturală și își calculează singur spectrograma log-Mel.
   - parametrul `preprocess=0` dezactivează VAD-ul (pentru comparația din evaluare)
3. **Extragere de trăsături:** MFCC (13 coeficienți). Spectrograma se generează **doar** în scripturile Python pentru documentație, nu se trimite la browser.
4. **Recunoaștere, două metode (comparate în documentație):**
   - **Metoda A, Whisper:** folosită în aplicație. Semnalul preprocesat → text.
   - **Metoda B, MFCC + DTW** (`recognizer_dtw.py`):
     - **șabloanele:** 3–5 per comandă în `speech/templates_audio/<acțiune>/`, înregistrate din `#/record`
     - **trăsăturile:** MFCC cu pre-emphasis + CMVN (medie 0, deviație 1 pe fiecare coeficient)
     - **DTW** scris explicit (accelerat cu `numba`), cu distanța normalizată la n + m
     - **clasificarea:** 1-NN; pragul de respingere e 1.5 × mediana distanței dintre șabloanele aceleiași comenzi, calculat automat; segmentele > 2.5 s se resping
     - DTW nu poate extrage numere: `timer` folosește timpul pasului curent
     - **Test sintetic (vocile Windows):** 22/22 corect pe aceeași voce, ~20 ms față de ~600 ms la Whisper; pe altă voce, 0/10 (DTW depinde de vorbitor)
   - Metoda se alege prin parametrul `method=whisper|dtw` (implicit `whisper`). **Nu există comutator în interfață.** Pentru demo, `http://localhost:8090/?method=dtw#/cook/1` folosește DTW. Comparația se face în `evaluate.py`.
5. **Interpretarea comenzii** (Whisper):
   - normalizare text: litere mici, fără diacritice, fără punctuație
   - căutare de cuvinte-cheie în dicționarul de comenzi, apoi `difflib.get_close_matches` ca rezervă
   - extragerea parametrilor numerici („timer 5 minutes” → `value: 5`), cu cifre și numere în cuvinte, în engleză și română
6. **Răspuns JSON:**
```json
{
  "action": "next",
  "value": null,
  "transcript": "next step please",
  "method": "whisper",
  "processing_ms": 840
}
```
Dacă fraza nu e o comandă: `"action": "unknown"`. Frontend-ul **o ignoră în liniște** și afișează doar o notă gri discretă „I heard: …”, ca să nu apară erori când vorbești normal în bucătărie.

## 6. Comenzi vocale (engleză și română)

| Acțiune | Exemple EN | Exemple RO |
|---|---|---|
| `next` | next, next step | următorul, pasul următor, înainte |
| `previous` | back, previous | înapoi, pasul anterior |
| `repeat` | repeat, again | repetă, din nou |
| `ingredients` | ingredients | ingrediente |
| `close` | close, hide | închide |
| `timer` | start timer [N minutes] | pornește timer [N minute] |
| `stop_timer` | stop timer | oprește timer |
| `read` | read, read step | citește |
| `help` | help, what can I say | ajutor, ce pot spune |
| `exit` | exit, quit, go home | ieșire, ieși, acasă |

- `timer` fără număr folosește timpul definit pe pasul curent.
- Dicționarul de comenzi stă într-un singur loc (`speech/commands.py`), ca să fie ușor de extins.

## 7. Frontend: funcționalități și design

### Stil
- Interfața e în **engleză**, în stil **warm & clean**: galben de unt `#F7D774`, crem `#FFF8E7`, maro cald, colțuri rotunjite, un **logo text** „Utter & Butter”.
- **Fără mascotă.** Mesajele pot fi prietenoase („Say ‘next step’ and let’s keep cooking!”).
- Ținta principală e **laptopul, citit de la ~2 m**: textul pasului ≥ 40 px. Layout-ul e responsive.
- Accesibilitate: contrast bun, `aria-label` pe butoane, `aria-live` pentru feedback.

### Pagini
- **Home (`#/`):** carduri cu rețetele (titlu, porții, timp total), plus butonul „+ New recipe”. Din card se poate edita sau șterge rețeta.
- **Formular (`#/new`, `#/edit/:id`):** titlu, porții, timp total, listă de ingrediente (add/remove) și listă de pași, fiecare cu un timer opțional în minute. Fără upload de imagini.
- **Modul de gătit (`#/cook/:id`):**
  - cardul pasului curent, foarte mare, plus „Step 2/6” și o bară de progres
  - **indicator de microfon** (listening / processing / paused / error), fără buton push-to-talk
  - un **mesaj scurt** cu comanda recunoscută („✓ Next step”), plus nota gri „I heard: …”
  - ingredientele apar într-un **overlay** la comanda `ingredients` și se închid cu `close`
  - **un singur timer.** Dacă pasul are timp, apare sugestia „Start 5 min”. La final se aude un sunet și ecranul clipește până la `stop_timer`.
  - butoane de rezervă pentru click: ◄ ►, ← Back
  - `next` pe ultimul pas duce la ecranul „Bon appétit! 🎉”, iar `exit` duce pe Home
- **Nu există** panou „Under the hood” și nici spectrogramă în interfață.

## 8. Teste și evaluare (pentru documentație)
Un script separat, `evaluation/evaluate.py`, care rulează pe un set de înregistrări etichetate (`evaluation/data/<quiet|noise>/<comanda>/*.wav`, înregistrate din `#/record`) și produce:
- **acuratețea** pe comenzi, pentru Whisper și pentru MFCC + DTW
- **timpul de procesare** mediu pe fiecare metodă
- rezultatele în **liniște** față de **zgomot de fundal** (de exemplu hotă, apă curgând, muzică)
- rezultatele cu și fără preprocesare (ca să se vadă efectul VAD-ului și al filtrării)
- o **matrice de confuzie** și grafice (PNG) în `evaluation/results/`

Implementare: rulează în containerul `speech` (`docker compose exec speech python /evaluation/evaluate.py`, opțional `--methods dtw`). Produce:
- `results.csv`
- `summary.md`, cu tabelul gata de copiat în documentație
- graficele `accuracy.png`, `processing_time.png` și `confusion_<metoda>_<conditie>.png`

**Rezultate pe setul sintetic** (vocea Windows David, 30 de fișiere în liniște + 30 cu zgomot la ~10 dB SNR):

| Metoda | Liniște | Zgomot | Timp |
|---|---|---|---|
| Whisper | 100% | 87% | ~620 ms |
| DTW cu VAD | 90% | 0% | ~35 ms |
| DTW fără VAD | 0% | 0% | ~35 ms |

- Fără VAD, cadrele de liniște strică alinierea, deci DTW are nevoie de VAD.
- În zgomot DTW respinge tot, pentru că șabloanele sunt curate.
- DTW nu recunoaște „start timer five minutes” pe baza șablonului „start timer”.

Rezultatele finale se fac pe vocea reală a utilizatorului.

Un script `evaluation/plot_signal.py` generează, pentru un WAV, forma de undă, energia, ZCR, zonele detectate de VAD, spectrograma și MFCC, ca figuri pentru documentație.

## 9. Structura proiectului
```
utter&butter/
├── CLAUDE.md
├── README.md                 # cum se pornește cu Docker Desktop
├── docker-compose.yml
├── web/
│   ├── Dockerfile            # nginx
│   ├── nginx.conf            # static + proxy /api/recipes → api, /api/command → speech
│   └── public/
│       ├── index.html
│       ├── style.css
│       ├── app.js            # router SPA, pagini
│       ├── api.js            # apeluri fetch către backend
│       ├── cooking.js        # modul de gătit, timer, acțiuni
│       └── listener.js       # ascultare continuă, segmentare, WAV 16 kHz
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py                # CRUD rețete (psycopg + SQL)
├── db/
│   └── init.sql              # tabele + rețete demo
├── speech/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py                # POST /api/command
│   ├── preprocessing.py      # DC, pre-emphasis, VAD (energie + ZCR), normalizare
│   ├── features.py           # MFCC, spectrogramă
│   ├── recognizer_whisper.py
│   ├── recognizer_dtw.py
│   ├── commands.py           # dicționar comenzi + interpretare text
│   └── templates_audio/      # șabloane WAV pentru DTW (per comandă)
└── evaluation/
    ├── plot_signal.py
    ├── evaluate.py
    ├── data/
    └── results/
```

## 10. Reguli de lucru pentru Claude Code
- **Codul trebuie să rămână simplu** (refactorizat pe 15 nov 2026 pentru un începător):
  - funcții scurte, fără abstracții inutile
  - în frontend, butoanele folosesc `data-action` și un singur handler de click
  - în backend, erorile de validare sunt `ValueError`, transformate automat în 400
- Lucrăm **incremental**, în pași mici care se pot testa. Ordinea:
  1. `docker-compose` cu `db` + `api` + `web` și o pagină simplă
  2. CRUD rețete: Home + formular
  3. UI-ul modului de gătit, cu butoane (fără voce încă)
  4. serviciul `speech` + ascultare continuă + Whisper + comenzi
  5. preprocesare explicită + `plot_signal.py`
  6. MFCC + DTW
  7. scriptul de evaluare
- **Explică** fiecare pas pe scurt, pe înțelesul unui începător. Comentariile din cod sunt în **română**, iar numele de variabile și funcții în **engleză**.
- Codul de prelucrare a semnalului se scrie **explicit** (de exemplu energia și ZCR calculate cu numpy), nu ascuns într-un singur apel de bibliotecă.
- Fără dependențe inutile și fără framework-uri frontend.
- După fiecare pas: comenzile exacte de rulare pe Windows (PowerShell + Docker Desktop) și ce ar trebui să se vadă.
- Aplicația se deschide la **`http://localhost:8090`**.
