---
tags: [utter-butter, python, semnal, materie]
---

# 08 Preprocesare și VAD

Înapoi la [[00 Start aici]] · vezi și [[07 Serviciul speech]]

Fișier: `speech/preprocessing.py`. Totul e scris **explicit cu numpy**, ca să poată fi explicat.

## 1. Citirea semnalului
`load_wav()`: WAV mono, 16 kHz, 16 biți → vector `float32`.
Eșantioanele sunt întregi între −32768 și 32767, așa că le împărțim la 2¹⁵ = 32768 → valori în **[−1, 1]**.

## 2. Eliminarea componentei DC
```
y[n] = x[n] − media(x)
```
Un microfon poate avea un decalaj constant față de zero. Nu conține informație vocală, dar mărește artificial energia cadrelor.

## 3. Analiza pe cadre scurte
Vocea se schimbă continuu, dar pe 20–30 ms e „aproape staționară”.
- **cadru** = 25 ms = 400 de eșantioane
- **pas** = 10 ms = 160 de eșantioane, deci cadrele se suprapun

`frame_signal()` întoarce o matrice `(număr_cadre, 400)`.

## 4. Energia pe termen scurt
```
E = (1/N) · Σ x[n]²        apoi în dB:  10 · log10(E)
```
Vorbirea are energie mare, liniștea are energie mică.

## 5. Zero-crossing rate (ZCR)
```
ZCR = (1/N) · numărul de perechi vecine cu semne diferite
```
În cod: două eșantioane vecine au semne diferite exact atunci când **produsul lor e negativ** (`x[n] · x[n−1] < 0`).
Arată de câte ori semnalul își schimbă semnul:
- **vocale** (sonore, periodice): ZCR mic (~0.02–0.1)
- **consoane fricative** (s, f, ș): ZCR mare (~0.3–0.5), dar energie mică
- **zgomot alb**: ZCR mare

## 6. VAD (Voice Activity Detection)
`detect_speech()`, inspirat din algoritmul **Rabiner–Sambur**.

**Praguri adaptive:**
- zgomot de fond = **percentila 10** a energiei (cele mai liniștite cadre)
- prag de jos = zgomot + **6 dB**
- prag de sus = zgomot + **12 dB**
- minimum absolut: −50 dBFS

**Regula pe fiecare cadru:**
- energie > prag de sus → **vorbire** (sigur e voce)
- energie > prag de jos **și** ZCR > **0.25** → **vorbire** (voce slabă, dar „șuierată”, de exemplu „s” din „start”)
- altfel → **liniște**

**E vorbire sau doar un zgomot scurt?** Fragmentul conține vorbire doar dacă are cel puțin **10 cadre de vorbire** (100 ms). Un clic sau un pocnet ține 2–3 cadre, deci e respins.

**Tăierea:** de la primul la ultimul cadru cu vorbire, plus o **margine de 150 ms**. Inițial marginea era de 50 ms, dar în zgomot tăia finalul cuvintelor („ingredients” → „in”). Evaluarea a arătat problema → [[12 Evaluare și grafice]].

**Dacă nu e vorbire**, Whisper nu mai rulează: răspunsul e `unknown`, în ~2 ms.

## 7. Normalizarea
Cel mai mare vârf devine 0.95. Vocea are același nivel indiferent de distanța față de microfon.

## 8. Pre-emphasis (doar pe ramura MFCC)
```
y[0] = x[0]
y[n] = x[n] − 0.97 · x[n−1]
```
Este un filtru trece-sus de ordinul 1: „ridică” frecvențele înalte (formanții superiori, consoanele).

**De ce NU înainte de Whisper:** Whisper a fost antrenat pe vorbire naturală și își calculează singur spectrograma log-Mel. Pre-emphasis se aplică doar pentru spectrogramă și MFCC → [[10 MFCC și DTW]].

## Ordinea finală
```
WAV → numpy → eliminare DC → VAD (energie + ZCR) → tăiere → normalizare → Whisper
                                                                        → pre-emphasis → MFCC → DTW
```

## Grafice
`evaluation/plot_signal.py` desenează pentru o înregistrare: forma de undă cu zona VAD, energia cu pragurile, ZCR cu pragul, semnalul curățat, spectrograma și MFCC → [[12 Evaluare și grafice]].
