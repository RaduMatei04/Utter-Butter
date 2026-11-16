---
tags: [utter-butter, frontend, date]
---

# 11 Voice recorder

Înapoi la [[00 Start aici]] · vezi și [[10 MFCC și DTW]], [[12 Evaluare și grafice]]

Fișier: `web/public/recorder.js` · adresă: `http://localhost:8090/#/record` (link discret jos pe Home)

## La ce folosește
Nu face parte din aplicația de gătit. E o **unealtă** pentru a-ți înregistra vocea, cu două scopuri:

| Set | Pentru ce | Unde se salvează |
|---|---|---|
| **Templates (MFCC + DTW)** | șabloanele metodei DTW. Fără ele, DTW nu poate rula. | `speech/templates_audio/<comanda>/` |
| **Test set → Quiet room** | evaluarea în liniște | `evaluation/data/quiet/<comanda>/` |
| **Test set → Background noise** | evaluarea cu hota, apa sau muzica pornită | `evaluation/data/noise/<comanda>/` |

În setul de test, timer-ul se spune **cu număr** („start timer five minutes”), ca să testăm și extragerea valorii.

## Cum se folosește
1. Alegi setul (și condiția, pentru test).
2. La o comandă apeși **Record 5** și o spui de 5 ori, cu pauză între ele. Rândul devine galben și butonul arată „Stop (n left)”.
3. Fiecare frază se salvează automat, iar coloana **Saved** crește. Verde = minimum 3.
4. **Undo last** șterge ultima înregistrare a comenzii (dacă ai greșit sau a intrat zgomot).

## Cum funcționează
- Refolosește `listener.js` în modul **`onSegment`**: în loc să ceară o comandă, primește fișierul WAV al fiecărei fraze → [[04 Ascultarea continuă (listener)]].
- Trimite fișierul la `POST /api/speech/recordings?set=...&action=...&condition=...` → [[07 Serviciul speech]].
- Serverul verifică cu VAD-ul că înregistrarea **conține vorbire**. Altfel răspunde „No speech detected, please try again”.
- La setul *Templates*, șabloanele DTW se reîncarcă imediat, deci comanda nouă se poate folosi pe loc.

## De ce o pagină web și nu un script Python
Din Docker, Python nu are acces la microfonul de pe Windows. Browserul are, iar înregistrarea trece prin exact același drum ca o comandă reală (aceeași segmentare, același format WAV). E un avantaj pentru evaluare.
