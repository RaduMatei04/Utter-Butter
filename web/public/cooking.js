// cooking.js: modul de gătit (#/cook/:id).
//
// Ideea principală: TOATE acțiunile trec prin funcția Cooking.handleAction(action, value).
//   - acum o apelăm din butoane și din tastatură;
//   - la pasul 4 o va apela și recunoașterea vocală, cu răspunsul de la server
//     (ex: {"action": "next"} sau {"action": "timer", "value": 5}).
// Așa interfața nu trebuie să știe dacă o comandă a venit din voce sau dintr-un click.
//
// Acțiuni: next, previous, repeat, ingredients, close, timer, stop_timer, read, help, exit

const Cooking = (() => {
  // ------------------------------------------------------------------
  // Starea modului de gătit
  // ------------------------------------------------------------------
  let recipe = null;        // rețeta curentă (de la backend)
  let stepIndex = 0;        // indexul pasului curent (0 = primul pas)
  let finished = false;     // true când am trecut de ultimul pas („Bon appétit!”)
  let overlay = null;       // ce panou e deschis: null, "ingredients" sau "help"

  // Timer-ul (unul singur)
  let timerRemaining = 0;   // secunde rămase
  let timerTotal = 0;       // secunde la pornire (pentru bara de progres)
  let timerInterval = null; // id-ul lui setInterval (null = timer oprit)
  let timerRinging = false; // true când timpul a expirat și sună alarma
  let alarmInterval = null;  // bipurile (null = alarma nu sună)
  let alarmTimeout = null;   // oprirea automată a alarmei
  let audioContext = null;   // pentru sunetul alarmei (Web Audio API)

  // Alarma sună cel mult 1 minut, apoi tace singură
  // (timer-ul rămâne afișat cu roșu „Time's up!”).
  const ALARM_MAX_MS = 60 * 1000;

  let feedbackTimeout = null;
  let root = null;          // elementul <main id="app">

  // Textele afișate după fiecare comandă recunoscută
  const FEEDBACK = {
    next: "Next step",
    previous: "Previous step",
    repeat: "Here it is again",
    ingredients: "Ingredients",
    close: "Closed",
    stop_timer: "Timer stopped",
    read: "Reading step",
    help: "Here's what you can say",
  };

  // ------------------------------------------------------------------
  // Pornire / oprire (apelate de router din app.js)
  // ------------------------------------------------------------------

  async function start(container, recipeId) {
    root = container;
    root.innerHTML = '<p class="muted">Loading recipe…</p>';

    try {
      recipe = await Api.getRecipe(recipeId);
    } catch (error) {
      root.innerHTML = `
        <div class="message-box">
          <p>Oops! ${escapeHtml(error.message)}</p>
          <a class="btn" href="#/">← Back to recipes</a>
        </div>`;
      return;
    }

    stepIndex = 0;
    finished = false;
    overlay = null;
    buildLayout();
    render();
    document.addEventListener("keydown", onKeyDown);

    // Pornim microfonul (vezi listener.js). Răspunsurile serverului ajung în onVoiceResult.
    Listener.start({
      onState: setMicState,
      onResult: onVoiceResult,
      onError: (message) => showFeedback(message, "warn"),
    });
  }

  // Răspunsul serviciului `speech`: {"action": "next", "value": null, "transcript": "..."}
  function onVoiceResult(result) {
    showHeard(result.transcript);
    if (result.action && result.action !== "unknown") {
      handleAction(result.action, result.value);
    }
    // "unknown" = conversație normală în bucătărie: o ignorăm în liniște
  }

  // Curățăm tot când părăsim pagina (altfel timer-ul ar continua în fundal)
  function stop() {
    Listener.stop();
    document.removeEventListener("keydown", onKeyDown);
    stopTimer(false);
    if (window.speechSynthesis) speechSynthesis.cancel();
    document.body.classList.remove("timer-ringing");
    recipe = null;
  }

  // ------------------------------------------------------------------
  // Punctul central: execută o acțiune
  // ------------------------------------------------------------------

  function handleAction(action, value = null) {
    if (!recipe) return;

    switch (action) {
      case "next":
        if (finished) break;
        if (stepIndex < recipe.steps.length - 1) {
          stepIndex++;
        } else {
          finished = true; // după ultimul pas -> ecranul „Bon appétit!”
        }
        overlay = null;
        break;

      case "previous":
        if (finished) {
          finished = false;           // din „Bon appétit!” revenim la ultimul pas
        } else if (overlay) {
          overlay = null;             // „back” cu un panou deschis = închide panoul
        } else if (stepIndex > 0) {
          stepIndex--;
        }
        break;

      case "repeat":
        overlay = null;
        flashStep();
        speak(currentStepText());
        break;

      case "ingredients":
        overlay = "ingredients";
        break;

      case "help":
        overlay = "help";
        break;

      case "close":
        overlay = null;
        break;

      case "timer": {
        // „start timer 5 minutes” -> value = 5
        // „start timer” fără număr -> folosim timpul pasului curent
        const minutes = value || currentStep()?.timer_minutes;
        if (!minutes) {
          showFeedback("This step has no timer. Try “start timer 5 minutes”", "warn");
          return;
        }
        startTimer(minutes);
        showFeedback(`Timer started: ${minutes} min`);
        render();
        return;
      }

      case "stop_timer":
        stopTimer(true);
        break;

      case "read":
        speak(currentStepText());
        break;

      case "exit":
        location.hash = "#/"; // router-ul apelează apoi stop()
        return;

      default:
        return; // acțiune necunoscută: o ignorăm în liniște
    }

    if (FEEDBACK[action]) showFeedback(FEEDBACK[action]);
    render();
  }

  // ------------------------------------------------------------------
  // Afișare
  // ------------------------------------------------------------------

  function currentStep() {
    return finished ? null : recipe.steps[stepIndex];
  }

  function currentStepText() {
    return finished ? "Bon appétit! Enjoy your meal." : recipe.steps[stepIndex].text;
  }

  // Scheletul paginii: îl construim o singură dată, apoi render() doar actualizează
  function buildLayout() {
    root.innerHTML = `
      <section class="cook">
        <div class="cook-top">
          <a class="btn btn-small" href="#/" aria-label="Back to recipes">← Back</a>
          <h1 class="cook-title">${escapeHtml(recipe.title)}</h1>
          <button id="mic-status" class="mic-status" data-state="off"
                  aria-label="Microphone status. Click to mute or unmute.">
            <span class="mic-dot" aria-hidden="true"></span>
            <span class="mic-label" aria-live="polite">Mic off</span>
          </button>
        </div>

        <div class="progress" aria-hidden="true"><div id="progress-bar" class="progress-bar"></div></div>

        <article id="step-card" class="step-card" aria-live="polite"></article>

        <div class="cook-controls">
          <button class="btn btn-round" id="btn-prev" aria-label="Previous step">◄</button>
          <div id="timer-area" class="timer-area"></div>
          <button class="btn btn-round btn-primary" id="btn-next" aria-label="Next step">►</button>
        </div>

        <div class="cook-bottom">
          <button class="btn btn-small" data-action="ingredients">🥚 Ingredients</button>
          <button class="btn btn-small" data-action="read">🔊 Read</button>
          <button class="btn btn-small" data-action="help">❓ Help</button>
        </div>

        <div id="feedback" class="feedback" role="status" aria-live="assertive"></div>
        <p id="heard" class="heard"></p>

        <div id="overlay" class="overlay" hidden></div>
      </section>`;

    // Click pe indicatorul de microfon = pornește / oprește ascultarea
    root.querySelector("#mic-status").addEventListener("click", () => Listener.toggle());

    // Butoanele trimit acțiuni, exact ca vocea
    root.querySelector("#btn-prev").addEventListener("click", () => handleAction("previous"));
    root.querySelector("#btn-next").addEventListener("click", () => handleAction("next"));
    root.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => handleAction(button.dataset.action));
    });
  }

  function render() {
    if (!root || !recipe) return;
    const total = recipe.steps.length;

    // Bara de progres
    const done = finished ? total : stepIndex + 1;
    root.querySelector("#progress-bar").style.width = `${(done / total) * 100}%`;

    // Cardul cu pasul curent (sau ecranul final)
    const card = root.querySelector("#step-card");
    if (finished) {
      card.className = "step-card step-card-done";
      card.innerHTML = `
        <p class="step-number">All done!</p>
        <p class="step-text">Bon appétit! 🎉</p>
        <div class="done-actions">
          <button class="btn" id="btn-again">Cook again</button>
          <a class="btn btn-primary" href="#/">Back to recipes</a>
        </div>`;
      card.querySelector("#btn-again").addEventListener("click", () => {
        finished = false;
        stepIndex = 0;
        render();
      });
    } else {
      const step = recipe.steps[stepIndex];
      card.className = "step-card";
      card.innerHTML = `
        <p class="step-number">Step ${stepIndex + 1} of ${total}</p>
        <p class="step-text">${escapeHtml(step.text)}</p>`;
    }

    // Butoanele ◄ ►: dezactivate când nu au sens
    root.querySelector("#btn-prev").disabled = !finished && stepIndex === 0;
    root.querySelector("#btn-next").disabled = finished;

    renderTimer();
    renderOverlay();
  }

  // Zona timer-ului: fie sugestia „Start 5 min”, fie numărătoarea inversă
  function renderTimer() {
    const area = root.querySelector("#timer-area");
    const step = currentStep();

    if (timerInterval || timerRinging) {
      const minutes = Math.floor(timerRemaining / 60);
      const seconds = String(timerRemaining % 60).padStart(2, "0");
      // Alarma a tăcut singură, dar timer-ul încă nu a fost închis
      const silenced = timerRinging && !alarmInterval;
      const timeText = silenced ? "Time's up!" : `${minutes}:${seconds}`;
      const buttonText = !timerRinging ? "Stop" : silenced ? "Dismiss" : "Stop alarm";
      area.innerHTML = `
        <div class="timer ${timerRinging ? "timer-done" : ""}" role="timer">
          <span class="timer-time">⏱ ${timeText}</span>
          <button class="btn btn-small" id="btn-stop-timer">${buttonText}</button>
        </div>`;
      area.querySelector("#btn-stop-timer").addEventListener("click", () => handleAction("stop_timer"));
    } else if (step && step.timer_minutes) {
      area.innerHTML = `
        <button class="btn btn-timer" id="btn-start-timer">⏱ Start ${step.timer_minutes} min</button>`;
      area.querySelector("#btn-start-timer").addEventListener("click", () => handleAction("timer"));
    } else {
      area.innerHTML = "";
    }
  }

  // Panourile peste ecran: ingrediente sau ajutor
  function renderOverlay() {
    const box = root.querySelector("#overlay");
    if (!overlay) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }

    let title, body;
    if (overlay === "ingredients") {
      title = "🥚 Ingredients";
      body = recipe.ingredients.length
        ? `<ul class="overlay-list">${recipe.ingredients.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`
        : '<p class="muted">This recipe has no ingredients listed.</p>';
    } else {
      title = "❓ What you can say";
      body = `
        <ul class="overlay-list help-list">
          <li><b>“Next step”</b> / “Pasul următor”</li>
          <li><b>“Back”</b> / “Înapoi”</li>
          <li><b>“Repeat”</b> / “Repetă”</li>
          <li><b>“Read”</b> / “Citește”</li>
          <li><b>“Ingredients”</b> / “Ingrediente”</li>
          <li><b>“Close”</b> / “Închide”</li>
          <li><b>“Start timer 5 minutes”</b> / “Pornește timer 5 minute”</li>
          <li><b>“Stop timer”</b> / “Oprește timer”</li>
          <li><b>“Exit”</b> / “Ieșire”</li>
        </ul>
        <p class="muted keys-hint">Keyboard: ← → steps · I ingredients · R read · T timer · S stop · H help · Esc close</p>`;
    }

    box.hidden = false;
    box.innerHTML = `
      <div class="overlay-panel" role="dialog" aria-modal="true" aria-label="${title}">
        <h2>${title}</h2>
        ${body}
        <button class="btn btn-primary" id="btn-close-overlay">Close</button>
        <p class="muted">or say “close”</p>
      </div>`;
    box.querySelector("#btn-close-overlay").addEventListener("click", () => handleAction("close"));
  }

  // Mesajul scurt după o comandă (ex: „✓ Next step”), dispare după 2 secunde
  function showFeedback(text, type = "ok") {
    const box = root?.querySelector("#feedback");
    if (!box) return;
    box.textContent = (type === "ok" ? "✓ " : "") + text;
    box.className = `feedback feedback-${type} feedback-show`;
    clearTimeout(feedbackTimeout);
    feedbackTimeout = setTimeout(() => box.classList.remove("feedback-show"), 2000);
  }

  // Nota gri „I heard: …” (o va folosi recunoașterea vocală la pasul 4)
  function showHeard(transcript) {
    const note = root?.querySelector("#heard");
    if (note) note.textContent = transcript ? `I heard: “${transcript}”` : "";
  }

  // Indicatorul de microfon: off / listening / processing / paused / error
  function setMicState(state, label) {
    const box = root?.querySelector("#mic-status");
    if (!box) return;
    box.dataset.state = state;
    box.querySelector(".mic-label").textContent = label;
  }

  // Animație scurtă pe card (pentru „repeat”)
  function flashStep() {
    const card = root.querySelector("#step-card");
    card.classList.remove("flash");
    void card.offsetWidth; // truc: forțează browserul să repornească animația
    card.classList.add("flash");
  }

  // ------------------------------------------------------------------
  // Timer
  // ------------------------------------------------------------------

  function startTimer(minutes) {
    stopTimer(false); // un singur timer: îl oprim pe cel vechi
    timerTotal = Math.max(1, Math.round(minutes * 60)); // secunde întregi
    timerRemaining = timerTotal;
    timerInterval = setInterval(tick, 1000); // tick() rulează la fiecare secundă
  }

  function tick() {
    timerRemaining--;
    if (timerRemaining <= 0) {
      timerRemaining = 0;
      clearInterval(timerInterval);
      timerInterval = null;
      startAlarm();
    }
    renderTimer();
  }

  function stopTimer(withRender) {
    clearInterval(timerInterval);
    timerInterval = null;
    timerRemaining = 0;
    stopAlarm();
    if (withRender) renderTimer();
  }

  // Alarma: un „bip” la fiecare secundă + ecranul clipește, până la „stop timer”
  function startAlarm() {
    timerRinging = true;
    document.body.classList.add("timer-ringing");
    beep();
    alarmInterval = setInterval(beep, 1000);
    alarmTimeout = setTimeout(silenceAlarm, ALARM_MAX_MS);
    showFeedback("Time's up! Say “stop timer”", "warn");
  }

  // Oprirea automată: tac bipurile și clipitul, dar „Time's up!” rămâne pe ecran
  function silenceAlarm() {
    clearInterval(alarmInterval);
    alarmInterval = null;
    document.body.classList.remove("timer-ringing");
    if (root && recipe) renderTimer();
  }

  function stopAlarm() {
    timerRinging = false;
    clearTimeout(alarmTimeout);
    alarmTimeout = null;
    silenceAlarm();
  }

  // Generăm un sunet scurt cu Web Audio API (un oscilator sinusoidal de 880 Hz)
  function beep() {
    try {
      audioContext = audioContext || new AudioContext();
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = 880; // nota La5
      gain.gain.setValueAtTime(0.3, audioContext.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.4);
      oscillator.connect(gain).connect(audioContext.destination);
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.4);
    } catch (error) {
      console.warn("Could not play the alarm sound", error);
    }
  }

  // ------------------------------------------------------------------
  // Citire cu voce (text-to-speech din browser)
  // ------------------------------------------------------------------

  function speak(text) {
    if (!window.speechSynthesis) return;
    speechSynthesis.cancel(); // oprim ce citea înainte
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    utterance.rate = 0.95;
    speechSynthesis.speak(utterance);
  }

  // ------------------------------------------------------------------
  // Scurtături de tastatură (utile la testare, înainte de partea de voce)
  // ------------------------------------------------------------------

  function onKeyDown(event) {
    // Nu interceptăm tastele când utilizatorul scrie într-un câmp
    if (event.target.matches("input, textarea")) return;

    const keyToAction = {
      ArrowRight: "next",
      ArrowLeft: "previous",
      Escape: "close",
      i: "ingredients",
      r: "read",
      t: "timer",
      s: "stop_timer",
      h: "help",
    };
    const action = keyToAction[event.key] || keyToAction[event.key.toLowerCase()];
    if (action) {
      event.preventDefault();
      handleAction(action);
    }
  }

  // Ce „exportăm” pentru celelalte fișiere
  return { start, stop, handleAction, showHeard, setMicState };
})();
