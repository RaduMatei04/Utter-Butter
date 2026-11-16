---
tags: [utter-butter, python, recunoastere, materie]
---

# 10 MFCC și DTW

Înapoi la [[00 Start aici]] · vezi și [[08 Preprocesare și VAD]], [[09 Whisper și interpretarea comenzilor]]

Fișiere: `speech/features.py`, `speech/recognizer_dtw.py`

## Metoda B: recunoaștere clasică, fără rețea neuronală
Pentru fiecare comandă avem 3–5 **șabloane** (înregistrări-model cu vocea ta), în `speech/templates_audio/<comanda>/`. Le înregistrezi din [[11 Voice recorder]].

O comandă nouă se compară cu toate șabloanele, iar câștigă **cel mai apropiat** (1-nearest-neighbour).

## Spectrograma (`spectrogram()`, explicit cu numpy)
Pentru fiecare cadru de 25 ms (pas 10 ms):
1. **fereastra Hamming**: `w[n] = 0.54 − 0.46·cos(2πn/(N−1))`. Atenuează marginile cadrului, ca tăietura bruscă să nu creeze frecvențe false.
2. **FFT** cu 512 puncte → spectrul cadrului
3. modulul în **dB**: `20·log10(|X|)`

Folosită doar în graficele pentru documentație.

## MFCC (`mfcc()`, cu librosa)
Mel-Frequency Cepstral Coefficients, pe semnalul cu **pre-emphasis**:
1. cadre de 25 ms + fereastră Hamming
2. FFT → spectrul de putere
3. **40 de filtre triunghiulare pe scala Mel**. Scala imită urechea: distinge bine frecvențele joase, mai slab pe cele înalte.
4. **logaritm**: urechea percepe intensitatea logaritmic
5. **DCT**: păstrăm primii **13 coeficienți**, care descriu anvelopa spectrului, adică forma tractului vocal

Rezultatul e o matrice `(13, număr_cadre)`: un vector la fiecare 10 ms.

**CMVN** (Cepstral Mean and Variance Normalization): pe fiecare coeficient scădem media și împărțim la deviația standard. Elimină diferențele „constante” (alt microfon, altă distanță, alt volum).

## DTW (Dynamic Time Warping), scris explicit
Problema: aceeași comandă e spusă de fiecare dată cu altă viteză. DTW găsește cea mai bună **aliniere în timp** între două secvențe: poate întinde sau comprima timpul.

```
D[0,0] = 0
D[i,j] = d(a_i, b_j) + min( D[i−1, j],      a avansează, b „stă pe loc”
                            D[i, j−1],      b avansează, a „stă pe loc”
                            D[i−1, j−1] )   avansează amândouă

distanța = D[n, m] / (n + m)      normalizată, pentru secvențe de lungimi diferite
```
`d` = distanța euclidiană între doi vectori MFCC.

`@numba.njit` compilează funcția în cod mașină. Două bucle `for` în Python pur ar fi de ~100 de ori mai lente.

## Decizia
- `scores[comanda]` = cea mai mică distanță DTW față de șabloanele comenzii
- câștigă comanda cu scorul minim
- **pragul de respingere** se calculează automat din șabloane:
  - pentru fiecare șablon, distanța până la cel mai apropiat alt șablon al aceleiași comenzi
  - **prag = 1.5 × mediana** acestor distanțe (`REJECT_FACTOR`)
  - peste prag → `unknown`
- segmentele mai lungi de **2.5 s** se resping, pentru că sunt conversație, nu comenzi

## Limitări (bune pentru documentație)
- **Depinde de vorbitor:** test cu voci sintetice, 22/22 corect pe vocea din care s-au făcut șabloanele și 0/10 pe altă voce.
- Știe **doar frazele fixe** din șabloane: „start timer five minutes” ≠ „start timer”.
- **Nu poate extrage numere**: `timer` folosește timpul pasului curent.
- **Sensibil la zgomot** dacă șabloanele sunt înregistrate în liniște.
- **Are nevoie de VAD:** fără tăierea liniștii, cadrele de liniște strică alinierea.

**Avantaje:** foarte rapid (~20–40 ms, față de ~600 ms la Whisper), fără rețea neuronală, merge cu 3–5 exemple.

## Cum îl încerci
- înregistrezi șabloanele la `http://localhost:8090/#/record` → [[11 Voice recorder]]
- modul de gătit cu DTW: `http://localhost:8090/?method=dtw#/cook/1`
