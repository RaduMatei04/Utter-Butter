---
tags: [utter-butter, schema, rezumat]
---

# 14 Schema logică, pe înțelesul tuturor

Înapoi la [[00 Start aici]]

> Pe scurt: **vorbești → aplicația te aude → curăță sunetul → ghicește ce comandă ai spus → face acel lucru pe ecran.**
> Rețetele stau într-o bază de date, ca într-un dulap cu sertare.

---

## 1. Imaginea mare

```mermaid
flowchart TB
    U(["👩‍🍳 Tu, în bucătărie"])
    subgraph BROWSER["🖥️ Browserul (ce vezi pe ecran)"]
        UI["Pagina aplicației<br/>rețete, pași, timer"]
        MIC["🎤 Urechea aplicației<br/>ascultă tot timpul"]
    end
    subgraph DOCKER["📦 Docker: 4 cutii care lucrează împreună"]
        WEB["🧑‍💼 web: recepționerul<br/>dă pagina, trimite cererile mai departe"]
        API["📚 api: bibliotecarul<br/>se ocupă de rețete"]
        DB[("🗄️ db: dulapul<br/>PostgreSQL")]
        SPEECH["🧠 speech: creierul<br/>înțelege vocea"]
    end

    U -- "apasă, scrie" --> UI
    U -- "vorbește" --> MIC
    UI -- "vreau rețetele" --> WEB
    MIC -- "uite ce am auzit (fișier audio)" --> WEB
    WEB --> API
    WEB --> SPEECH
    API <--> DB
    SPEECH -- "ai zis: «next»" --> UI
    API -- "uite rețetele" --> UI
```

**Cine ce face:**

| Cutia | Pe înțeles | Termenul tehnic |
|---|---|---|
| **web** | recepționerul: îți dă pagina și duce fiecare cerere la omul potrivit | server nginx, reverse proxy |
| **api** | bibliotecarul: aduce, pune, schimbă și aruncă rețete | server Flask (Python), REST API |
| **db** | dulapul cu sertare unde stau rețetele | PostgreSQL |
| **speech** | creierul care ascultă și înțelege | Flask + Whisper + MFCC/DTW |

Toate patru pornesc deodată cu o singură comandă: `docker compose up`. Docker e ca un set de **cutii închise**: fiecare are înăuntru tot ce îi trebuie ca să meargă.

---

## 2. Cum ajung rețetele în PostgreSQL

### Dulapul are 3 sertare

```mermaid
flowchart LR
    R["🗂️ Sertarul REȚETE<br/>nr. 1: Pancakes, 4 porții, 30 min"]
    I["🥚 Sertarul INGREDIENTE<br/>«2 eggs», aparține rețetei nr. 1<br/>«500 ml milk», aparține rețetei nr. 1"]
    S["📝 Sertarul PAȘI<br/>pasul 1: «Whisk the eggs», rețeta nr. 1<br/>pasul 3: «Let it rest», rețeta nr. 1, timer 10 min"]
    R -- "legate prin numărul rețetei" --> I
    R -- "legate prin numărul rețetei" --> S
```

- Fiecare ingredient și fiecare pas are pe el **numărul rețetei** de care aparține, ca o etichetă.
- Dacă arunci o rețetă, se aruncă automat și ingredientele, și pașii ei. Tehnic: `ON DELETE CASCADE`.

### De unde vin datele

```mermaid
flowchart TB
    subgraph START["La prima pornire"]
        A1["db/init.sql<br/>(o listă de instrucțiuni)"] --> A2["construiește sertarele<br/>și pune 3 rețete demo"]
    end
    subgraph ADD["Când adaugi o rețetă"]
        B1["completezi formularul<br/>titlu, ingrediente, pași"] --> B2["browserul trimite datele<br/>(format JSON)"]
        B2 --> B3["api le verifică:<br/>are titlu? are măcar un pas?"]
        B3 --> B4["api le scrie în sertare<br/>(comenzi SQL: INSERT)"]
    end
    subgraph READ["Când deschizi o rețetă"]
        C1["browserul cere rețeta nr. 3"] --> C2["api o caută în sertare<br/>(comenzi SQL: SELECT)"]
        C2 --> C3["o trimite înapoi<br/>și ea apare pe ecran"]
    end
    A2 --> DB[("🗄️ PostgreSQL")]
    B4 --> DB
    DB --> C2
```

Pe scurt, bibliotecarul (`api`) vorbește cu dulapul (`db`) într-o limbă specială, **SQL**:
- **INSERT** = „pune în sertar”
- **SELECT** = „caută în sertar”
- **UPDATE** = „schimbă”
- **DELETE** = „aruncă”

Datele rămân salvate chiar dacă oprești aplicația. Tehnic: stau într-un *volum Docker*.

---

## 3. Cum e construită interfața

### O singură pagină care își schimbă conținutul

Aplicația e **o singură pagină web**. Ce vezi depinde de ce scrie după `#` în adresă:

```mermaid
flowchart LR
    H["#/<br/>🏠 Home<br/>cardurile cu rețete"]
    N["#/new<br/>📝 Formular<br/>rețetă nouă"]
    E["#/edit/3<br/>✏️ Formular<br/>editezi rețeta 3"]
    C["#/cook/3<br/>🍳 Modul de gătit<br/>rețeta 3, cu microfon"]
    R["#/record<br/>🎙️ Înregistrarea<br/>vocii tale"]
    H -- "+ New recipe" --> N
    H -- "Edit" --> E
    H -- "Cook" --> C
    H -- "link jos" --> R
    N -- "Save" --> H
    E -- "Save" --> H
    C -- "«exit» / Back" --> H
```

Pagina nu se reîncarcă. Doar partea din mijloc se redesenează din JavaScript. Tehnic: **SPA** (Single Page Application), cu un **router** care citește `#`.

Fișierele, pe scurt:
- `index.html` = scheletul (bara de sus + un loc gol în mijloc)
- `style.css` = hainele (culori de unt, colțuri rotunde, text mare)
- `app.js` = „dirijorul” care alege pagina
- `cooking.js` = modul de gătit
- `listener.js` = urechea
- `recorder.js` = pagina de înregistrare

### Modul de gătit: o singură „ușă” pentru toate comenzile

```mermaid
flowchart LR
    V["🗣️ Vocea<br/>«next step»"] --> D
    B["🖱️ Un buton<br/>►"] --> D
    K["⌨️ O tastă<br/>săgeata →"] --> D
    D{"🚪 handleAction<br/>(«next»)"} --> X["ecranul arată<br/>pasul următor"]
```

Nu contează **cum** dai comanda: vocea, butonul și tastatura intră toate pe **aceeași ușă**. De aceea vocea se poate adăuga peste o interfață care merge deja și cu click-uri.

---

## 4. Ce se întâmplă când spui „next step”

```mermaid
flowchart TB
    S1["1) 🗣️ Spui «next step»"]
    S2["2) 🎤 Urechea (listener.js) observă că s-a făcut<br/>mai zgomot decât de obicei → începe o frază"]
    S3["3) După ~0,7 s de liniște, fraza s-a terminat"]
    S4["4) Sunetul e micșorat la 16.000 de măsurători pe secundă<br/>și împachetat într-un fișier WAV"]
    S5["5) 📦 Fișierul pleacă la creier (speech)"]
    S6["6) 🧹 Curățare: se taie liniștea, se egalizează volumul"]
    S7{"7) E vorbire<br/>sau doar zgomot?"}
    S8["8) 🧠 Recunoaștere<br/>(Whisper SAU MFCC + DTW)"]
    S9["9) ✅ Răspuns: action = «next»"]
    S10["10) 🍳 Ecranul trece la pasul următor"]
    Z["🔇 Ignorat"]
    S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7
    S7 -- "zgomot (clic, tuse)" --> Z
    S7 -- "vorbire" --> S8 --> S9 --> S10
```

Tot drumul durează **sub o secundă**.

---

## 5. Curățarea sunetului (VAD)

**Problema:** fișierul are liniște la început și la sfârșit, iar uneori doar un zgomot (o ușă trântită). Vrem doar bucata în care cineva vorbește.

**Cum facem:** tăiem sunetul în **felii foarte subțiri, de 25 de milisecunde** (ca o pâine feliată). Pentru fiecare felie ne uităm la două lucruri:

| Măsurăm | Pe înțeles | Ce ne spune |
|---|---|---|
| **Energia** | cât de **tare** e felia | vocea e mai tare decât liniștea |
| **ZCR** (treceri prin zero) | cât de **„șuierat”** e sunetul: de câte ori unda trece de la plus la minus | „s”, „f”, „ș” sunt slabe, dar foarte șuierate |

```mermaid
flowchart LR
    F["o felie de 25 ms"] --> Q1{"e TARE?"}
    Q1 -- da --> V["✅ vorbire"]
    Q1 -- nu --> Q2{"e puțin tare<br/>ȘI șuierată?"}
    Q2 -- da --> V
    Q2 -- nu --> L["⬜ liniște"]
```

- **„Tare” e relativ la cameră.** Aplicația măsoară întâi zgomotul de fond, adică cele mai liniștite felii, și compară totul cu el.
- **La final** păstrăm doar zona dintre prima și ultima felie cu vorbire, plus o mică margine.
- **Dacă sunt sub 10 felii de vorbire** (adică sub 0,1 secunde), a fost doar un clic, deci îl ignorăm.

Tehnic: **VAD** (Voice Activity Detection), cu *energie pe termen scurt* și *zero-crossing rate*.

---

## 6. Cele două „creiere” care recunosc comanda

### 🅰️ Whisper: creierul care știe să citească

```mermaid
flowchart LR
    A["🔊 sunetul curățat"] --> W["🤖 Whisper<br/>(rețea neuronală)"]
    W --> T["📝 text:<br/>«Next step, please.»"]
    T --> C["🔎 caută cuvinte cunoscute<br/>«next step» → next"]
    C --> R["✅ next"]
```

- **Ce e Whisper:** un program care a „ascultat” sute de mii de ore de vorbire și a învățat să **transforme orice frază în text**, ca un stenograf.
- **După el**, textul e comparat cu un **dicționar de comenzi** („next”, „pasul următor”, „înapoi”...). Dacă găsește una, gata.
- **Numerele** („five”, „cinci”) se transformă în cifre, pentru timer.
- **Plus:** înțelege orice formulare, în engleză și română. **Minus:** e mai lent (~0,6 s).

### 🅱️ MFCC + DTW: creierul care compară „amprente”

Metoda clasică, fără inteligență artificială. Pe scurt: **„sună la fel ca exemplele pe care mi le-ai dat?”**

**Pasul 0: îi dai exemple.** Spui fiecare comandă de 5 ori (pagina `#/record`). Acestea sunt **șabloanele**.

**Pasul 1, MFCC: „amprenta” sunetului**

```mermaid
flowchart LR
    A["🔊 sunetul"] --> F["felii de 25 ms"]
    F --> SP["🌈 pentru fiecare felie:<br/>ce frecvențe (grave / ascuțite)<br/>are și cât de tare"]
    SP --> MEL["👂 le grupăm ca urechea:<br/>multe grupe la grave,<br/>puține la ascuțite"]
    MEL --> N["🔢 rezumăm felia<br/>în 13 numere"]
    N --> FP["🧬 amprenta:<br/>13 numere la fiecare 10 ms"]
```

- Fiecare felie de sunet devine **13 numere** care descriu **„forma” vocii** în acel moment: ce sunet faci cu gura („a”, „e”, „s”...).
- Un cuvânt de o secundă devine un **șir de ~100 de astfel de amprente mici**.
- Tehnic, *MFCC* = Mel-Frequency Cepstral Coefficients:
  - spectrul se calculează cu FFT
  - frecvențele se grupează pe scala Mel, „ca urechea”
  - urmează logaritm, apoi DCT
- Înainte, sunetul trece printr-un filtru care **accentuează sunetele ascuțite** (consoanele). Tehnic: *pre-emphasis*.

**Pasul 2, DTW: compari două șiruri spuse cu viteze diferite**

Problema: o dată spui „neeext” rar, altă dată „next” repede. Nu le poți compara felie cu felie, pentru că nu se aliniază.

```mermaid
flowchart TB
    subgraph EX["Exemplu: același cuvânt, două viteze"]
        A1["șablonul tău:   n - e - x - t"]
        A2["ce ai spus acum: n - e - e - e - x - t"]
    end
    EX --> D["🪢 DTW întinde și comprimă timpul ca pe un elastic,<br/>ca «e»-ul lung să se potrivească peste «e»-ul scurt"]
    D --> SC["📏 după aliniere, adună cât de diferite<br/>sunt amprentele → o DISTANȚĂ<br/>(mică = seamănă mult)"]
```

Tehnic: *Dynamic Time Warping*. Găsește drumul cel mai ieftin într-un tabel de comparații.

**Pasul 3: alegi cel mai apropiat șablon**

```mermaid
flowchart LR
    Q["🗣️ ce ai spus acum"] --> C1["distanța față de șabloanele «next»: 0,6 ✅ cea mai mică"]
    Q --> C2["distanța față de șabloanele «help»: 2,1"]
    Q --> C3["distanța față de șabloanele «exit»: 2,4"]
    C1 --> R{"0,6 e sub prag?"}
    R -- da --> OK["✅ next"]
    R -- nu --> NO["🔇 unknown<br/>(nu seamănă cu nimic)"]
```

- **Câștigă comanda cu distanța cea mai mică.**
- **Pragul:** dacă nici cea mai bună nu e destul de aproape, răspunsul e „nu știu”. Pragul se calculează singur, din cât de diferit spui tu de obicei aceeași comandă.

### Comparația celor două creiere

|  | 🅰️ Whisper | 🅱️ MFCC + DTW |
|---|---|---|
| Cum gândește | transformă vocea în text, apoi citește | compară amprenta cu exemplele tale |
| Are nevoie de exemple? | nu | da, 5 pe comandă |
| Înțelege orice frază? | da | doar frazele din exemple |
| Înțelege numere („5 minutes”)? | da | nu |
| Merge pe altă voce? | da | aproape deloc |
| Viteză | ~0,6 s | ~0,03 s (de ~20 de ori mai rapid) |
| Inteligență artificială? | da (rețea neuronală) | nu (matematică clasică) |

---

## 7. Tot lanțul, într-o singură poză

```mermaid
flowchart LR
    V["🗣️ voce"] --> E["🎤 ureche<br/>(browser)"]
    E --> W["📦 fișier WAV"]
    W --> C["🧹 curățare<br/>(energie + ZCR)"]
    C --> A["🅰️ Whisper → text"]
    C --> B["🅱️ MFCC → DTW"]
    A --> K["✅ comandă"]
    B --> K
    K --> U["🍳 acțiune<br/>pe ecran"]
```

Exact asta cere tema: **semnal vocal → prelucrare → text / trăsături → comandă → acțiune în interfață.**

Detaliile fiecărei bucăți sunt în notițele [[01 Arhitectura generală]] … [[13 Rulare și depanare]].
