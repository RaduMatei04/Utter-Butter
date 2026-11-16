// recorder.js: pagina #/record, pentru înregistrarea vocii tale.
//
//   Templates  -> șabloanele metodei MFCC + DTW     (speech/templates_audio/<comanda>/)
//   Test set   -> înregistrări pentru evaluate.py   (evaluation/data/<quiet|noise>/<comanda>/)
//
// Microfonul ascultă continuu (listener.js). Apeși „Record 5” la o comandă,
// iar următoarele 5 fraze spuse se salvează pentru ea.

const Recorder = (() => {
  // [comanda, ce spui în engleză, ce spui în română]
  const COMMANDS = [
    ["next", "next step", "pasul următor"], ["previous", "go back", "înapoi"],
    ["repeat", "repeat", "repetă"], ["read", "read", "citește"],
    ["ingredients", "ingredients", "ingrediente"], ["close", "close", "închide"],
    ["timer", "start timer", "pornește timer"], ["stop_timer", "stop timer", "oprește timer"],
    ["help", "help", "ajutor"], ["exit", "exit", "ieșire"],
  ];
  const TAKES = 5;

  let root = null;
  let set = "templates";       // "templates" sau "test"
  let condition = "quiet";     // "quiet" sau "noise" (doar pentru setul de test)
  let recording = null;        // comanda pe care o înregistrăm acum
  let left = 0;                // câte fraze mai sunt de spus
  let counts = {};             // câte înregistrări are fiecare comandă

  // În setul de test, timer-ul se spune cu un număr (testăm și extragerea lui)
  function phrase(action) {
    if (set === "test" && action === "timer") return ["start timer five minutes", "pornește timer cinci minute"];
    return COMMANDS.find(([a]) => a === action).slice(1);
  }

  function url(path, action = "") {
    return `/api/speech/recordings${path}?set=${set}&condition=${condition}&action=${action}`;
  }

  async function start(container) {
    root = container;
    recording = null;
    root.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Voice recorder</h1>
          <p class="subtitle">Record your own voice for the MFCC + DTW templates and for the evaluation test set.</p>
        </div>
        <button id="mic-status" class="mic-status" data-action="mic" data-state="off">
          <span class="mic-dot"></span><span class="mic-label">Mic off</span>
        </button>
      </div>
      <div class="recorder-options">
        <label>Set
          <select id="set">
            <option value="templates">Templates (MFCC + DTW)</option>
            <option value="test">Test set (evaluation)</option>
          </select>
        </label>
        <label id="condition-label">Condition
          <select id="condition">
            <option value="quiet">Quiet room</option>
            <option value="noise">Background noise (hood, water, music)</option>
          </select>
        </label>
      </div>
      <p id="status" class="recorder-status" role="status">
        Click “Record ${TAKES}” next to a command, then say it ${TAKES} times with a short pause between.
      </p>
      <table class="recorder-table">
        <thead><tr><th>Command</th><th>Say</th><th>Saved</th><th></th></tr></thead>
        <tbody id="rows"></tbody>
      </table>`;

    root.querySelector("#set").value = set;
    root.querySelector("#condition").value = condition;
    root.querySelector("#set").onchange = (e) => { set = e.target.value; recording = null; refresh(); };
    root.querySelector("#condition").onchange = (e) => { condition = e.target.value; recording = null; refresh(); };

    // Toate butoanele din pagină au data-action
    root.onclick = (event) => {
      const button = event.target.closest("[data-action]");
      if (!button) return;
      const action = button.dataset.command;
      if (button.dataset.action === "mic") Listener.toggle();
      if (button.dataset.action === "record") toggleRecording(action);
      if (button.dataset.action === "undo") undo(action);
    };

    await refresh();
    Listener.start({ onState: showMicState, onSegment: save, onError: (message) => showStatus(message, true) });
  }

  function stop() {
    if (!root) return;
    Listener.stop();
    root.onclick = null;
    root = null;
  }

  async function refresh() {
    counts = await fetch(url("")).then((r) => r.json());
    render();
  }

  function render() {
    root.querySelector("#condition-label").hidden = set !== "test";
    root.querySelector("#rows").innerHTML = COMMANDS.map(([action]) => {
      const [en, ro] = phrase(action);
      const n = counts[action] || 0;
      const active = recording === action;
      return `
        <tr class="${active ? "armed" : ""}">
          <td><code>${action}</code></td>
          <td><b>“${en}”</b><br><span class="muted">or “${ro}”</span></td>
          <td><span class="count ${n >= 3 ? "count-ok" : ""}">${n}</span></td>
          <td><div class="row-actions">
            <button class="btn btn-small ${active ? "btn-danger" : "btn-primary"}" data-action="record" data-command="${action}">
              ${active ? `Stop (${left} left)` : `Record ${TAKES}`}</button>
            <button class="btn btn-small" data-action="undo" data-command="${action}" ${n ? "" : "disabled"}>Undo last</button>
          </div></td>
        </tr>`;
    }).join("");
  }

  function toggleRecording(action) {
    recording = recording === action ? null : action;
    left = TAKES;
    if (recording) showStatus(`Say “${phrase(action)[0]}” now (${left} left)…`);
    render();
  }

  async function undo(action) {
    counts = await fetch(url("/last", action), { method: "DELETE" }).then((r) => r.json());
    showStatus("Last recording deleted.");
    render();
  }

  // listener.js ne dă fiecare frază spusă, ca fișier WAV
  async function save(wav) {
    if (!recording || !root) return;   // nu înregistrăm nimic acum: ignorăm fraza
    const action = recording;
    const form = new FormData();
    form.append("audio", wav, "sample.wav");

    const response = await fetch(url("", action), { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) return showStatus(data.error, true);

    counts = data;
    left--;
    if (left === 0) recording = null;
    showStatus(left === 0 ? `✓ Done with “${phrase(action)[0]}”. Pick the next command.`
                          : `✓ Saved. Say “${phrase(action)[0]}” again (${left} left)…`);
    render();
  }

  function showStatus(text, isWarning = false) {
    const box = root?.querySelector("#status");
    if (!box) return;
    box.textContent = text;
    box.dataset.type = isWarning ? "warn" : "ok";
  }

  function showMicState(state, label) {
    const box = root?.querySelector("#mic-status");
    if (!box) return;
    box.dataset.state = state;
    box.querySelector(".mic-label").textContent = label;
  }

  return { start, stop };
})();
