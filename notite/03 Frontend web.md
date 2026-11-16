---
tags: [utter-butter, frontend]
---

# 03 Frontend web

Înapoi la [[00 Start aici]] · vezi și [[01 Arhitectura generală]]

## Ce e
O **SPA** (Single Page Application) în **HTML + CSS + JavaScript simplu**, fără framework și fără build. Pagina se încarcă o singură dată, iar conținutul se schimbă din JavaScript.

## Fișierele (`web/public/`)

| Fișier | Rol |
|---|---|
| `index.html` | scheletul: bara de sus cu logo + `<main id="app">`, unde se desenează paginile |
| `style.css` | tot designul: culori, butoane, carduri, formular, modul de gătit, recorder |
| `api.js` | toate apelurile `fetch()` către backend, într-un singur obiect `Api` |
| `app.js` | **router-ul** + paginile Home și formular |
| `cooking.js` | modul de gătit → [[05 Modul de gătit]] |
| `listener.js` | microfonul → [[04 Ascultarea continuă (listener)]] |
| `recorder.js` | pagina de înregistrare → [[11 Voice recorder]] |

Ordinea scripturilor în `index.html` contează: `api.js`, `listener.js`, `cooking.js`, `recorder.js`, apoi `app.js` (care le folosește pe toate).

## Router-ul (în `app.js`)
Partea de după `#` din adresă alege pagina:

| Adresă | Pagină |
|---|---|
| `#/` | Home: cardurile cu rețete (Cook / Edit / Delete) |
| `#/new` | formular pentru o rețetă nouă |
| `#/edit/3` | formular completat cu rețeta 3 |
| `#/cook/3` | modul de gătit pentru rețeta 3 |
| `#/record` | Voice recorder |

Cum funcționează:
1. `window.addEventListener("hashchange", router)`: browserul anunță când se schimbă `#`.
2. `router()` desparte adresa (`"#/edit/3"` → `["edit", "3"]`) și apelează funcția paginii.
3. Înainte de orice pagină: `Cooking.stop()` și `Recorder.stop()` opresc microfonul, timer-ul și citirea cu voce.

## Paginile
- **Home** (`renderHome`): cere lista la `GET /api/recipes` și construiește cardurile. *Delete* cere confirmare (`confirm()`).
- **Formular** (`renderForm`): titlu, porții, timp total, listă dinamică de ingrediente, listă de pași cu timer opțional (⏱ minute). La *Save* trimite `POST` (rețetă nouă) sau `PUT` (editare), apoi revine pe Home.

Detalii care merită explicate:
- **`escapeHtml()`:** orice text scris de utilizator e „curățat” înainte de a fi pus în HTML, ca un titlu de genul `<b>x</b>` să apară ca text.
- **`form.elements.title`** și nu `form.title`: `form.title` e atributul „title” al formularului, nu câmpul nostru. Era o greșeală reală, corectată.

## Design
- Stil **warm & clean**: galben de unt `#F7D774`, crem `#FFF8E7`, maro `#5A3E2B`, colțuri rotunjite, butoane „pastilă”. Logo doar text, fără mascotă.
- Culorile sunt variabile CSS (`:root { --butter: ... }`), deci se schimbă dintr-un singur loc.
- **Accesibilitate:**
  - `aria-label` pe butoane
  - `aria-live` pentru mesajele care apar
  - contur vizibil la navigarea cu tastatura (`:focus-visible`)
  - text mare în modul de gătit

## nginx
`web/nginx.conf` face două lucruri:
1. servește fișierele din `web/public/`;
2. e **reverse proxy**, adică trimite mai departe cererile:
   - `/api/command` și `/api/speech/...` → `speech:5001`
   - restul de `/api/...` → `api:5000`

Așa browserul vorbește cu **o singură adresă** (`localhost:8090`) și nu există probleme de CORS.

`resolver 127.0.0.11` + numele serviciilor în variabile: nginx caută serviciile la fiecare cerere, nu la pornire. Fără asta, nginx refuza să pornească dacă `speech` nu era încă gata.
