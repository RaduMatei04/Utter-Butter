---
tags: [utter-butter, frontend, audio]
---

# 04 Ascultarea continuă (listener)

Înapoi la [[00 Start aici]] · vezi și [[03 Frontend web]], [[07 Serviciul speech]]

Fișier: `web/public/listener.js`

## Ce face
În modul de gătit microfonul e **mereu pornit** („always listening”, fără wake word). Browserul trebuie să își dea seama singur **când începe și când se termină o frază**, și să trimită doar acea bucată la server.

> Aici e doar o **segmentare grosieră**, ca să știm ce trimitem. VAD-ul „adevărat” (energie + ZCR) se face în Python → [[08 Preprocesare și VAD]].

## Pașii
1. **`getUserMedia`**: cere acces la microfon.
   - `echoCancellation: true`: reduce sunetele aplicației, ca alarma sau vocea care citește
   - `noiseSuppression: false`: filtrarea o facem noi, în Python
2. **Web Audio API**: un `AudioContext` + `ScriptProcessorNode` primesc sunetul în bucăți de 2048 de eșantioane (~43 ms la 48 kHz).
3. Pentru fiecare bucată se calculează **RMS** (nivelul): `RMS = √( (1/N) · Σ x[n]² )`.
4. **Prag adaptiv**: `prag = max(0.012, 3 × zgomot_de_fond)`. Zgomotul de fond se actualizează lent, cât e liniște (medie exponențială: `zgomot = 0.95·zgomot + 0.05·nivel`).
5. **Mașina de stări:**
   - *liniște*: păstrăm ultimele ~300 ms (**pre-roll**), ca să nu pierdem începutul cuvântului
   - nivel > prag → *vorbire*: adunăm bucățile
   - ~700 ms de liniște sau maximum 5 s → segmentul se închide
   - sub 200 ms de vorbire → ignorăm segmentul (clic, tuse)
6. **Reeșantionare 48 kHz → 16 kHz** (`downsample`): fiecare eșantion nou e media eșantioanelor vechi din intervalul lui. Media lucrează ca un filtru trece-jos simplu și reduce aliasing-ul.
7. **Codare WAV** (`encodeWav`): antet de 44 de octeți scris „de mână” (RIFF, fmt, data) + eșantioane pe 16 biți.
8. **Trimitere:** `POST /api/command?method=whisper` cu `FormData`.

## Detalii utile
- **Pauză cât vorbește aplicația:** dacă `speechSynthesis.speaking`, nu ascultăm (+600 ms după), altfel aplicația s-ar auzi pe ea însăși.
- **Cât timp așteptăm răspunsul** (`busy`), nu înregistrăm segmente noi.
- **Stările** indicatorului din colț: `listening` (punct verde pulsând), `processing` („Thinking…”), `paused`, `error` („Mic blocked”). Click pe indicator = mute/unmute.
- **`?method=dtw`** în adresă (`http://localhost:8090/?method=dtw#/cook/1`) trimite comenzile la metoda MFCC + DTW → [[10 MFCC și DTW]].
- **Modul „onSegment”:** pagina [[11 Voice recorder]] refolosește același listener, dar în loc să ceară o comandă, primește fișierul WAV și îl salvează.
- **Dacă ai ieșit din pagină cât se aștepta un răspuns**, `callbacks` s-a schimbat între timp, iar răspunsul vechi e ignorat.
