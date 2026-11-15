// recorder.js: pagina #/record, unealtă pentru înregistrarea vocii tale.
//
//   - Templates (DTW): 3–5 exemple pentru fiecare comandă, folosite de metoda MFCC + DTW
//                      -> salvate în speech/templates_audio/<comanda>/
//   - Test set:        înregistrări etichetate pentru evaluate.py (pasul 7),
//                      în liniște sau cu zgomot de fond
//                      -> salvate în evaluation/data/<conditie>/<comanda>/
//
// Microfonul ascultă continuu (același listener.js ca la gătit). Când apeși
// „Record 5” la o comandă, următoarele 5 fraze spuse se salvează pentru ea.

const Recorder = (() => {
  // Ce trebuie spus pentru fiecare comandă (engleză / română)
  const PHRASES = [
    ["next", "next step", "pasul următor"],
    ["previous", "go back", "înapoi"],
    ["repeat", "repeat", "repetă"],
    ["read", "read", "citește"],
    ["ingredients", "ingredients", "ingrediente"],
    ["close", "close", "închide"],
    ["timer", "start timer", "pornește timer"],
    ["stop_timer", "stop timer", "oprește timer"],
    ["help", "help", "ajutor"],
    ["exit", "exit", "ieșire"],
  ];
  // În setul de test, timer-ul se spune cu un număr (testăm și extragerea valorii)
  const TEST_TIMER_PHRASE = ["start timer five minutes", "pornește timer cinci minute"];
  const TAKES = 5; // câte înregistrări la un click

  let root = null;
  let setName = "templates";   // "templates" sau "test"
  let condition = "quiet";     // "quiet" sau "noise" (doar pentru test)
  let armedAction = null;      // comanda pentru care înregistrăm acum
  let remaining = 0;           // câte înregistrări mai sunt de făcut
  let counts = {};

  // Fraza în engleză pentru o comandă (pentru mesajele de stare)
  function phraseFor(action) {
    if (setName === "test" && action === "timer") return TEST_TIMER_PHRASE[0];
    return PHRASES.find(([a]) => a === action)[1];
  }

  function query(extra = {}) {
    const params = new URLSearchParams({ set: setName, condition, ...extra });
    return params.toString();
  }

  async function start(container) {
    root = container;
    armedAction = null;
    root.innerHTML = `
      <section class="recorder">
        <div class="page-header">
          <div>
            <h1>Voice recorder</h1>
            <p class="subtitle">Record your own voice for the MFCC + DTW templates and for the evaluation test set.</p>
          </div>
          <button id="mic-status" class="mic-status" data-state="off" aria-label="Microphone status. Click to mute or unmute.">
            <span class="mic-dot" aria-hidden="true"></span>
            <span class="mic-label" aria-live="polite">Mic off</span>
          </button>
        </div>

        <div class="recorder-options">
          <label>Set
            <select id="set-select">
              <option value="templates">Templates (MFCC + DTW)</option>
              <option value="test">Test set (evaluation)</option>
            </select>
          </label>
          <label id="condition-label" hidden>Condition
            <select id="condition-select">
              <option value="quiet">Quiet room</option>
              <option value="noise">Background noise (hood, water, music)</option>
            </select>
          </label>
        </div>

        <p id="recorder-status" class="recorder-status" role="status" aria-live="polite">
          Click “Record ${TAKES}” next to a command, then say it ${TAKES} times with a short pause between.
        </p>

        <table class="recorder-table">
          <thead><tr><th>Command</th><th>Say</th><th>Saved</th><th></th></tr></thead>
          <tbody id="recorder-rows"></tbody>
        </table>
      </section>`;

    root.querySelector("#set-select").addEventListener("change", (e) => {
      setName = e.target.value;
      root.querySelector("#condition-label").hidden = setName !== "test";
      disarm();
      refresh();
    });
    root.querySelector("#condition-select").addEventListener("change", (e) => {
      condition = e.target.value;
      disarm();
      refresh();
    });
    root.querySelector("#mic-status").addEventListener("click", () => Listener.toggle());

    root.querySelector("#set-select").value = setName;
    root.querySelector("#condition-select").value = condition;
    root.querySelector("#condition-label").hidden = setName !== "test";

    await refresh();

    Listener.start({
      onState: (state, label) => {
        const box = root?.querySelector("#mic-status");
        if (!box) return;
        box.dataset.state = state;
        box.querySelector(".mic-label").textContent = label;
      },
      onSegment: saveSegment,
    });
  }

  function stop() {
    if (!root) return;
    Listener.stop();
    root = null;
  }

  // Citește de la server câte înregistrări are fiecare comandă și redesenează tabelul
  async function refresh() {
    try {
      const response = await fetch(`/api/speech/recordings?${query()}`);
      counts = await response.json();
    } catch {
      counts = {};
      setStatus("Cannot reach the speech service. Is Docker running?", "warn");
    }
    renderRows();
  }

  function renderRows() {
    const body = root?.querySelector("#recorder-rows");
    if (!body) return;
    body.innerHTML = PHRASES.map(([action, en, ro]) => {
      if (setName === "test" && action === "timer") [en, ro] = TEST_TIMER_PHRASE;
      const n = counts[action] || 0;
      const armed = armedAction === action;
      return `
        <tr class="${armed ? "armed" : ""}">
          <td><code>${action}</code></td>
          <td><b>“${en}”</b><br><span class="muted">or “${ro}”</span></td>
          <td><span class="count ${n >= 3 ? "count-ok" : ""}">${n}</span></td>
          <td class="row-actions">
            <button class="btn btn-small ${armed ? "btn-danger" : "btn-primary"}" data-record="${action}">
              ${armed ? `Stop (${remaining} left)` : `Record ${TAKES}`}
            </button>
            <button class="btn btn-small" data-undo="${action}" ${n === 0 ? "disabled" : ""}>Undo last</button>
          </td>
        </tr>`;
    }).join("");

    body.querySelectorAll("[data-record]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.record;
        if (armedAction === action) {
          disarm();
        } else {
          armedAction = action;
          remaining = TAKES;
          setStatus(`Say “${phraseFor(action)}” now (${remaining} left)…`);
        }
        renderRows();
      });
    });

    body.querySelectorAll("[data-undo]").forEach((button) => {
      button.addEventListener("click", async () => {
        const response = await fetch(`/api/speech/recordings/last?${query({ action: button.dataset.undo })}`, { method: "DELETE" });
        if (response.ok) counts = await response.json();
        setStatus("Last recording deleted.");
        renderRows();
      });
    });
  }

  function disarm() {
    armedAction = null;
    remaining = 0;
  }

  // listener.js ne dă fiecare frază spusă, ca fișier WAV
  async function saveSegment(wav) {
    if (!armedAction || !root) return; // nu înregistrăm nimic: ignorăm

    const action = armedAction;
    const form = new FormData();
    form.append("audio", wav, "sample.wav");

    try {
      const response = await fetch(`/api/speech/recordings?${query({ action })}`, { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) {
        setStatus(`${data.error || "Could not save"}`, "warn");
        return;
      }
      counts = data;
      remaining--;
      if (remaining <= 0) {
        disarm();
        setStatus(`✓ Done with “${phraseFor(action)}”. Pick the next command.`);
      } else {
        setStatus(`✓ Saved. Say “${phraseFor(action)}” again (${remaining} left)…`);
      }
    } catch {
      setStatus("Cannot reach the speech service.", "warn");
    }
    renderRows();
  }

  function setStatus(text, type = "ok") {
    const box = root?.querySelector("#recorder-status");
    if (!box) return;
    box.textContent = text;
    box.dataset.type = type;
  }

  return { start, stop };
})();
