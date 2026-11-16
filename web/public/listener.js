// listener.js: microfonul ascultă continuu și trimite fiecare frază la server.
//
// 1. Citim sunetul de la microfon în bucăți mici (~40 ms).
// 2. Pentru fiecare bucată calculăm nivelul (RMS) și îl comparăm cu un prag.
// 3. Nivel peste prag = începe o frază. ~700 ms de liniște = fraza s-a terminat.
// 4. Fraza e convertită în WAV (16 kHz, 16 biți) și trimisă la serviciul `speech`.
//
// Aici facem doar o tăiere grosieră. Prelucrarea „adevărată” (VAD cu energie + ZCR) e în Python.

const Listener = (() => {
  const PRE_ROLL_MS = 300;       // păstrăm și 300 ms dinainte, ca să nu pierdem începutul cuvântului
  const END_SILENCE_MS = 700;    // atâta liniște închide fraza
  const MAX_PHRASE_MS = 5000;    // o frază are cel mult 5 secunde
  const MIN_SPEECH_MS = 200;     // mai puțin = un clic sau o tuse, o ignorăm

  // ?method=dtw în adresă = folosim metoda MFCC + DTW în loc de Whisper
  const METHOD = new URLSearchParams(location.search).get("method") === "dtw" ? "dtw" : "whisper";

  let callbacks = null;          // { onState, onResult, onError, onSegment } de la pagina care ascultă
  let stream = null;             // microfonul
  let audioContext = null;
  let muted = false;
  let busy = false;              // așteptăm răspunsul serverului
  let pausedUntil = 0;           // după ce aplicația a vorbit, mai așteptăm puțin
  let currentState = "";

  // Starea frazei curente
  let chunks = [];               // bucățile de sunet adunate
  let speaking = false;          // suntem în mijlocul unei fraze?
  let speechMs = 0;
  let silenceMs = 0;
  let noiseLevel = 0.005;        // zgomotul de fond, se adaptează la cameră

  async function start(newCallbacks) {
    stop();
    callbacks = newCallbacks;
    currentState = "";
    const myCallbacks = callbacks;
    setState("processing", "Starting mic…");

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: false },
      });
    } catch {
      setState("error", "Mic blocked");
      return;
    }
    if (callbacks !== myCallbacks) {          // între timp am ieșit din pagină
      stream.getTracks().forEach((track) => track.stop());
      return;
    }

    audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(2048, 1, 1);   // ne dă bucăți de 2048 eșantioane
    processor.onaudioprocess = (event) => onChunk(new Float32Array(event.inputBuffer.getChannelData(0)));
    source.connect(processor);
    processor.connect(audioContext.destination);

    if (audioContext.state === "suspended") {
      setState("paused", "Click to start listening");   // browserul vrea un click înainte de sunet
    } else {
      setState("listening", "Listening");
    }
  }

  function stop() {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    if (audioContext) audioContext.close();
    stream = audioContext = callbacks = null;
    busy = false;
    resetPhrase();
  }

  // Click pe indicatorul de microfon: pornește sunetul sau comută mute
  function toggle() {
    if (!audioContext) return;
    if (audioContext.state === "suspended") {
      audioContext.resume();
      muted = false;
    } else {
      muted = !muted;
    }
    resetPhrase();
    setState(muted ? "paused" : "listening", muted ? "Muted · click to listen" : "Listening");
  }

  function resetPhrase() {
    chunks = [];
    speaking = false;
    speechMs = 0;
    silenceMs = 0;
  }

  // Apelată pentru fiecare bucată de sunet (~40 ms)
  function onChunk(chunk) {
    if (muted || busy || audioContext.state !== "running") return;

    // Cât timp aplicația citește cu voce (+ încă 600 ms), nu ascultăm: s-ar auzi pe ea însăși
    if (speechSynthesis.speaking) pausedUntil = performance.now() + 600;
    if (performance.now() < pausedUntil) {
      resetPhrase();
      setState("paused", "Paused while reading");
      return;
    }
    setState("listening", "Listening");

    const chunkMs = (chunk.length / audioContext.sampleRate) * 1000;
    const level = rms(chunk);
    const threshold = Math.max(0.012, noiseLevel * 3);
    chunks.push(chunk);

    if (!speaking) {
      if (level > threshold) {
        speaking = true;                                      // începe o frază
      } else {
        noiseLevel = 0.95 * noiseLevel + 0.05 * level;        // învățăm zgomotul de fond
        while (chunks.length * chunkMs > PRE_ROLL_MS) chunks.shift();
        return;
      }
    }

    if (level > threshold) {
      speechMs += chunkMs;
      silenceMs = 0;
    } else {
      silenceMs += chunkMs;
    }

    const phraseEnded = silenceMs >= END_SILENCE_MS || chunks.length * chunkMs >= MAX_PHRASE_MS;
    if (phraseEnded) {
      const enoughSpeech = speechMs >= MIN_SPEECH_MS;
      const samples = joinChunks(chunks);
      const sampleRate = audioContext.sampleRate;
      resetPhrase();
      if (enoughSpeech) send(toWav(downsample(samples, sampleRate, 16000), 16000));
    }
  }

  async function send(wav) {
    const myCallbacks = callbacks;
    busy = true;
    setState("processing", "Thinking…");

    try {
      if (callbacks.onSegment) {
        await callbacks.onSegment(wav);       // pagina #/record vrea doar fișierul
      } else {
        const form = new FormData();
        form.append("audio", wav, "command.wav");
        const response = await fetch(`/api/command?method=${METHOD}`, { method: "POST", body: form });
        const data = await response.json();
        if (callbacks !== myCallbacks) return;            // am ieșit din pagină între timp
        if (response.ok) callbacks.onResult(data);
        else callbacks.onError(data.error || "Server error");
      }
    } catch {
      if (callbacks === myCallbacks) callbacks.onError("Cannot reach the speech server");
    } finally {
      if (callbacks === myCallbacks) busy = false;
    }
  }

  function setState(state, label) {
    if (!callbacks || label === currentState) return;   // anunțăm pagina doar când se schimbă ceva
    currentState = label;
    callbacks.onState(state, label);
  }

  // ------------------------------------------------------------------
  // Prelucrări simple de semnal
  // ------------------------------------------------------------------

  // RMS = rădăcina din media pătratelor = „cât de tare” e sunetul
  function rms(samples) {
    let sum = 0;
    for (const s of samples) sum += s * s;
    return Math.sqrt(sum / samples.length);
  }

  function joinChunks(list) {
    const result = new Float32Array(list.reduce((n, c) => n + c.length, 0));
    let offset = 0;
    for (const c of list) {
      result.set(c, offset);
      offset += c.length;
    }
    return result;
  }

  // 48 kHz -> 16 kHz: fiecare eșantion nou = media a 3 eșantioane vechi.
  // Media lucrează și ca un filtru trece-jos simplu.
  function downsample(samples, fromRate, toRate) {
    const ratio = fromRate / toRate;
    const result = new Float32Array(Math.floor(samples.length / ratio));
    for (let i = 0; i < result.length; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.floor((i + 1) * ratio);
      let sum = 0;
      for (let j = start; j < end; j++) sum += samples[j];
      result[i] = sum / (end - start);
    }
    return result;
  }

  // Fișier WAV = antet de 44 de octeți + eșantioanele ca întregi pe 16 biți
  function toWav(samples, sampleRate) {
    const view = new DataView(new ArrayBuffer(44 + samples.length * 2));
    const text = (offset, str) => [...str].forEach((ch, i) => view.setUint8(offset + i, ch.charCodeAt(0)));

    text(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    text(8, "WAVE");
    text(12, "fmt ");
    view.setUint32(16, 16, true);              // mărimea blocului „fmt”
    view.setUint16(20, 1, true);               // 1 = PCM (necomprimat)
    view.setUint16(22, 1, true);               // 1 canal (mono)
    view.setUint32(24, sampleRate, true);      // eșantioane pe secundă
    view.setUint32(28, sampleRate * 2, true);  // octeți pe secundă
    view.setUint16(32, 2, true);               // octeți pe eșantion
    view.setUint16(34, 16, true);              // biți pe eșantion
    text(36, "data");
    view.setUint32(40, samples.length * 2, true);

    samples.forEach((s, i) => {
      const clipped = Math.max(-1, Math.min(1, s));
      view.setInt16(44 + i * 2, clipped * 32767, true);   // [-1, 1] -> [-32767, 32767]
    });
    return new Blob([view], { type: "audio/wav" });
  }

  return { start, stop, toggle };
})();
