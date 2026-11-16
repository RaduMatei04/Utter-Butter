---
tags: [utter-butter, evaluare, documentatie]
---

# 12 Evaluare și grafice

Înapoi la [[00 Start aici]] · vezi și [[08 Preprocesare și VAD]], [[10 MFCC și DTW]], [[11 Voice recorder]]

Fișiere: `evaluation/plot_signal.py`, `evaluation/evaluate.py`. Ambele rulează **în containerul `speech`**, care are deja numpy, librosa și matplotlib.

## `plot_signal.py`: analiza unei înregistrări
```powershell
docker compose exec speech python /evaluation/plot_signal.py                      # ultima comandă spusă
docker compose exec speech python /evaluation/plot_signal.py /evaluation/recordings/xxx.wav
```
Produce `evaluation/results/<nume>_analysis.png`, cu 6 grafice:
1. **forma de undă** (fără DC) + zona găsită de VAD
2. **energia pe termen scurt** (dB) + pragul de jos, pragul de sus, zgomotul de fond
3. **ZCR** + pragul de 0.25
4. **semnalul după preprocesare** (tăiat + normalizat), adică ce primește Whisper
5. **spectrograma** (pre-emphasis, Hamming, FFT 512)
6. **MFCC** (13 coeficienți; fiecare rând normalizat doar pentru afișare)

Bune pentru capitolul despre prelucrarea semnalului. Fă-le pe **vocea ta**, din `evaluation/recordings/`.

## `evaluate.py`: comparația metodelor
```powershell
docker compose exec speech python /evaluation/evaluate.py
docker compose exec speech python /evaluation/evaluate.py --methods dtw    # doar DTW, rapid
```
Are nevoie de **setul de test** și de **șabloane**, ambele din [[11 Voice recorder]].

Pentru fiecare fișier rulează toate combinațiile: **metodă** (Whisper / DTW) × **preprocesare** (cu / fără VAD), iar fișierele sunt grupate pe **condiții** (liniște / zgomot). Comandă recunoscută = eticheta (numele folderului)? → corect.

Rezultate în `evaluation/results/`:

| Fișier | Ce conține |
|---|---|
| `results.csv` | fiecare fișier: predicția, textul, timpul |
| `summary.md` | **tabelul gata de copiat în documentație** |
| `accuracy.png` | bare grupate: metodă × condiție × preprocesare. Fără preprocesare = bare hașurate. |
| `processing_time.png` | timpul mediu pe metodă (cu deviația standard) |
| `confusion_<metoda>_<conditie>.png` | matricea de confuzie, în procente pe rând |


## Rezultate pe setul sintetic (verificarea scriptului)
60 de fișiere cu vocea Windows David: 30 în liniște și 30 cu zgomot de hotă la ~10 dB SNR.

| Metoda | Liniște | Zgomot | Timp |
|---|---|---|---|
| Whisper | 100% | 87% | ~620 ms |
| DTW cu VAD | 90% | 0% | ~35 ms |
| DTW fără VAD | 0% | 0% | ~35 ms |

Concluzii (de verificat pe vocea ta):
- Whisper e robust, dar de ~20 de ori mai lent.
- **DTW are nevoie de VAD.**
- DTW nu suportă zgomotul când șabloanele sunt înregistrate în liniște. Nu confundă comenzi, le respinge.
- **Evaluarea a dus la o îmbunătățire.** În zgomot, VAD-ul tăia finalul cuvintelor slabe. Am mărit marginea de la 50 la 150 ms, iar Whisper în zgomot a urcat de la 80% la 87% → [[08 Preprocesare și VAD]].

> ⚠️ Rezultatele finale pentru documentație trebuie făcute pe **înregistrările tale reale**.
