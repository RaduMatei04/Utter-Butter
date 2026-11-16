// cooking.js: modul de gătit (#/cook/:id).
//
// Ideea principală: TOATE comenzile trec prin handleAction(action, value).
// Nu contează dacă vin din voce, din tastatură sau dintr-un click:
//   voce:       serverul răspunde {"action": "next"}  -> handleAction("next")
//   butoane:    <button data-action="next">           -> handleAction("next")
//   tastatură:  săgeata dreapta                       -> handleAction("next")

const Cooking = (() => {
  const ALARM_MAX_MS = 60 * 1000;   // alarma sună cel mult 1 minut, apoi tace singură

  // Mesajul scurt afișat după fiecare comandă
  const FEEDBACK = {
    next: "Next step", previous: "Previous step", repeat: "Here it is again",
    ingredients: "Ingredients", help: "Here's what you can say", close: "Closed",
    read: "Reading step", stop_timer: "Timer stopped",
  };

  const KEYS = {
    ArrowRight: "next", ArrowLeft: "previous", Escape: "close",
    i: "ingredients", h: "help", r: "read", t: "timer", s: "stop_timer",
  };

  const HELP = [
    ["Next step", "Pasul următor"], ["Back", "Înapoi"], ["Repeat", "Repetă"], ["Read", "Citește"],
    ["Ingredients", "Ingrediente"], ["Close", "Închide"], ["Start timer 5 minutes", "Pornește timer 5 minute"],
    ["Stop timer", "Oprește timer"], ["Exit", "Ieșire"],
  ];

  let root = null;          // elementul <main id="app">
  let recipe = null;
  let step = 0;             // pasul curent (0 = primul)
  let finished = false;     // am trecut de ultimul pas („Bon appétit!”)
  let panel = null;         // panoul deschis: null, "ingredients" sau "help"

  // Timer-ul (unul singur)
  let secondsLeft = 0;
  let ticking = null;       // setInterval-ul care scade secundele
  let timeUp = false;       // timpul a expirat
  let ringing = null;       // setInterval-ul care bipăie
  let alarmOff = null;      // setTimeout-ul care oprește alarma după 1 minut
  let audio = null;         // pentru bip (Web Audio API)

  // ------------------------------------------------------------------
  // Pornire / oprire (apelate de router, din app.js)
  // ------------------------------------------------------------------

  async function start(container, recipeId) {
    root = container;
    root.innerHTML = '<p class="muted">Loading recipe…</p>';
    try {
      recipe = await Api.getRecipe(recipeId);
    } catch (error) {
      root.innerHTML = `<div class="message-box"><p>Oops! ${escapeHtml(error.message)}</p>
                        <a class="btn" href="#/">← Back to recipes</a></div>`;
      return;
    }

    step = 0;
    finished = false;
    panel = null;
    root.innerHTML = layout();
    render();

    // Orice click pe un element cu data-action devine o comandă
    root.onclick = (event) => {
      const button = event.target.closest("[data-action]");
      if (button) handleAction(button.dataset.action);
    };
    document.addEventListener("keydown", onKey);

    // Microfonul (vezi listener.js)
    Listener.start({
      onState: showMicState,
      onResult: onVoice,
      onError: (message) => showFeedback(message, true),
    });
  }

  function stop() {
    if (!root) return;
    Listener.stop();
    stopTimer();
    speechSynthesis.cancel();
    document.removeEventListener("keydown", onKey);
    root.onclick = null;
    root = recipe = null;
  }

  // Răspunsul serverului de voce
  function onVoice(result) {
    root.querySelector("#heard").textContent = result.transcript ? `I heard: “${result.transcript}”` : "";
    // "unknown" = conversație normală în bucătărie: o ignorăm în liniște
    if (result.action !== "unknown") handleAction(result.action, result.value);
  }

  function onKey(event) {
    const action = KEYS[event.key] || KEYS[event.key.toLowerCase()];
    if (action) handleAction(action);
  }

  // ------------------------------------------------------------------
  // Punctul central: execută o comandă
  // ------------------------------------------------------------------

  function handleAction(action, value = null) {
    if (!recipe) return;
    const lastStep = recipe.steps.length - 1;

    switch (action) {
      case "next":
        if (step < lastStep) step++;
        else finished = true;
        panel = null;
        break;
      case "previous":
        if (panel) panel = null;                 // „back” cu un panou deschis îl închide
        else if (finished) finished = false;
        else if (step > 0) step--;
        break;
      case "repeat":
      case "read":
        panel = null;
        speak(finished ? "Bon appétit!" : recipe.steps[step].text);
        break;
      case "ingredients":
      case "help":
        panel = action;
        break;
      case "close":
        panel = null;
        break;
      case "timer": {
        // „start timer 5 minutes” -> value = 5; fără număr, folosim timpul pasului
        const minutes = value || (!finished && recipe.steps[step].timer_minutes);
        if (!minutes) return showFeedback("This step has no timer. Try “start timer 5 minutes”", true);
        startTimer(minutes);
        showFeedback(`Timer started: ${minutes} min`);
        break;
      }
      case "stop_timer":
        stopTimer();
        break;
      case "exit":
        location.hash = "#/";                    // router-ul apelează apoi stop()
        return;
      case "restart":                            // butonul „Cook again”
        step = 0;
        finished = false;
        break;
      case "mic":                                // click pe indicatorul de microfon
        Listener.toggle();
        return;
      default:
        return;                                  // comandă necunoscută: nu facem nimic
    }

    if (FEEDBACK[action]) showFeedback(FEEDBACK[action]);
    render();
    if (action === "repeat") {
      const card = root.querySelector("#step-card");
      card.classList.remove("flash");
      void card.offsetWidth;                     // truc: repornește animația CSS
      card.classList.add("flash");
    }
  }

  // ------------------------------------------------------------------
  // Afișare
  // ------------------------------------------------------------------

  // Scheletul paginii, construit o singură dată; render() completează părțile care se schimbă
  function layout() {
    return `
      <section class="cook">
        <div class="cook-top">
          <a class="btn btn-small" href="#/">← Back</a>
          <h1 class="cook-title">${escapeHtml(recipe.title)}</h1>
          <button id="mic-status" class="mic-status" data-action="mic" data-state="off"
                  aria-label="Microphone. Click to mute or unmute.">
            <span class="mic-dot"></span><span class="mic-label" aria-live="polite">Mic off</span>
          </button>
        </div>
        <div class="progress"><div id="progress-bar" class="progress-bar"></div></div>
        <article id="step-card" class="step-card" aria-live="polite"></article>
        <div class="cook-controls">
          <button id="btn-prev" class="btn btn-round" data-action="previous" aria-label="Previous step">◄</button>
          <div id="timer-area" class="timer-area"></div>
          <button id="btn-next" class="btn btn-round btn-primary" data-action="next" aria-label="Next step">►</button>
        </div>
        <div class="cook-bottom">
          <button class="btn btn-small" data-action="ingredients">🥚 Ingredients</button>
          <button class="btn btn-small" data-action="read">🔊 Read</button>
          <button class="btn btn-small" data-action="help">❓ Help</button>
        </div>
        <div id="feedback" class="feedback" role="status"></div>
        <p id="heard" class="heard"></p>
        <div id="panel" class="overlay" hidden></div>
      </section>`;
  }

  function render() {
    const total = recipe.steps.length;
    const card = root.querySelector("#step-card");

    root.querySelector("#progress-bar").style.width = `${((finished ? total : step + 1) / total) * 100}%`;
    root.querySelector("#btn-prev").disabled = step === 0 && !finished;
    root.querySelector("#btn-next").disabled = finished;

    card.classList.toggle("step-card-done", finished);
    card.innerHTML = finished
      ? `<p class="step-number">All done!</p>
         <p class="step-text">Bon appétit! 🎉</p>
         <div class="done-actions">
           <button class="btn" data-action="restart">Cook again</button>
           <a class="btn btn-primary" href="#/">Back to recipes</a>
         </div>`
      : `<p class="step-number">Step ${step + 1} of ${total}</p>
         <p class="step-text">${escapeHtml(recipe.steps[step].text)}</p>`;

    renderTimer();
    renderPanel();
  }

  function renderTimer() {
    const area = root.querySelector("#timer-area");
    const stepMinutes = finished ? null : recipe.steps[step].timer_minutes;

    if (ticking || timeUp) {
      const clock = `${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, "0")}`;
      const time = timeUp && !ringing ? "Time's up!" : clock;
      const label = !timeUp ? "Stop" : ringing ? "Stop alarm" : "Dismiss";
      area.innerHTML = `
        <div class="timer ${timeUp ? "timer-done" : ""}" role="timer">
          <span class="timer-time">⏱ ${time}</span>
          <button class="btn btn-small" data-action="stop_timer">${label}</button>
        </div>`;
    } else if (stepMinutes) {
      area.innerHTML = `<button class="btn btn-timer" data-action="timer">⏱ Start ${stepMinutes} min</button>`;
    } else {
      area.innerHTML = "";
    }
  }

  function renderPanel() {
    const box = root.querySelector("#panel");
    box.hidden = !panel;
    if (!panel) return;

    const items = panel === "ingredients"
      ? recipe.ingredients.map((item) => `<li>${escapeHtml(item)}</li>`)
      : HELP.map(([en, ro]) => `<li><b>“${en}”</b> / “${ro}”</li>`);

    box.innerHTML = `
      <div class="overlay-panel" role="dialog" aria-modal="true">
        <h2>${panel === "ingredients" ? "🥚 Ingredients" : "❓ What you can say"}</h2>
        <ul class="overlay-list ${panel === "help" ? "help-list" : ""}">${items.join("")}</ul>
        <button class="btn btn-primary" data-action="close">Close</button>
        <p class="muted">or say “close”</p>
      </div>`;
  }

  // Mesajul scurt de jos („✓ Next step”), dispare după 2 secunde
  let feedbackTimeout = null;
  function showFeedback(text, isWarning = false) {
    const box = root?.querySelector("#feedback");
    if (!box) return;
    box.textContent = isWarning ? text : `✓ ${text}`;
    box.className = `feedback feedback-show ${isWarning ? "feedback-warn" : ""}`;
    clearTimeout(feedbackTimeout);
    feedbackTimeout = setTimeout(() => box.classList.remove("feedback-show"), 2000);
  }

  // Indicatorul de microfon: listening / processing / paused / error
  function showMicState(state, label) {
    const box = root?.querySelector("#mic-status");
    if (!box) return;
    box.dataset.state = state;
    box.querySelector(".mic-label").textContent = label;
  }

  // ------------------------------------------------------------------
  // Timer și alarmă
  // ------------------------------------------------------------------

  function startTimer(minutes) {
    stopTimer();                                  // un singur timer: îl oprim pe cel vechi
    secondsLeft = Math.max(1, Math.round(minutes * 60));
    ticking = setInterval(() => {
      secondsLeft--;
      if (secondsLeft <= 0) {
        clearInterval(ticking);
        ticking = null;
        startAlarm();
      }
      renderTimer();
    }, 1000);
  }

  // Alarma: un bip pe secundă + ecranul clipește, până la „stop timer” (sau maxim 1 minut)
  function startAlarm() {
    timeUp = true;
    document.body.classList.add("timer-ringing");
    beep();
    ringing = setInterval(beep, 1000);
    alarmOff = setTimeout(silenceAlarm, ALARM_MAX_MS);
    showFeedback("Time's up! Say “stop timer”", true);
  }

  // Tac bipurile, dar „Time's up!” rămâne pe ecran până la Dismiss
  function silenceAlarm() {
    clearInterval(ringing);
    ringing = null;
    document.body.classList.remove("timer-ringing");
    if (recipe) renderTimer();
  }

  function stopTimer() {
    clearInterval(ticking);
    clearTimeout(alarmOff);
    ticking = null;
    timeUp = false;
    silenceAlarm();
  }

  // Bip scurt: un oscilator sinusoidal de 880 Hz, care se stinge în 0.4 s
  function beep() {
    audio = audio || new AudioContext();
    const oscillator = audio.createOscillator();
    const volume = audio.createGain();
    oscillator.frequency.value = 880;
    volume.gain.setValueAtTime(0.3, audio.currentTime);
    volume.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.4);
    oscillator.connect(volume).connect(audio.destination);
    oscillator.start();
    oscillator.stop(audio.currentTime + 0.4);
  }

  // Citire cu voce (text-to-speech din browser)
  function speak(text) {
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    speechSynthesis.speak(utterance);
  }

  return { start, stop, handleAction };
})();
