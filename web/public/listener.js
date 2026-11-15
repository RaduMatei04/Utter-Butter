// listener.js: ascultare continuă la microfon („always listening”).
//
// Ce face:
//   1. citește continuu sunetul de la microfon, în bucăți mici (~40 ms);
//   2. pentru fiecare bucată calculează nivelul (RMS) și îl compară cu un prag
//      care se adaptează la zgomotul de fond din cameră;
//   3. când nivelul trece de prag, începe un „segment” (cineva vorbește);
//      păstrăm și ~300 ms dinainte, ca să nu pierdem începutul cuvântului;
//   4. după ~700 ms de liniște (sau maximum 5 s) segmentul se închide;
//   5. segmentul e convertit la 16 kHz, WAV, 16 biți, și trimis la serviciul `speech`.
//
// Atenție: aici e doar o segmentare GROSIERĂ, ca să știm ce bucăți trimitem.
// VAD-ul „adevărat” (energie + ZCR) și toată prelucrarea se fac în Python.

const Listener = (() => {
  // ---------------- Parametri (se pot regla) ----------------
  const TARGET_RATE = 16000;     // Hz: ce așteaptă serverul
  const BUFFER_SIZE = 2048;      // eșantioane per bucată (~43 ms la 48 kHz)
  const PRE_ROLL_MS = 300;       // cât păstrăm dinainte de începutul vorbirii
  const END_SILENCE_MS = 700;    // câtă liniște închide un segment
  const MAX_SEGMENT_MS = 5000;   // lungimea maximă a unui segment
  const MIN_SPEECH_MS = 200;     // segmente mai scurte = zgomot (clic, tuse), le ignorăm
  const MIN_THRESHOLD = 0.012;   // pragul minim absolut de RMS
  const NOISE_FACTOR = 3;        // pragul = de 3 ori nivelul zgomotului de fond
  const TTS_COOLDOWN_MS = 600;   // după ce aplicația termină de vorbit, mai așteptăm puțin

  // ---------------- Starea ----------------
  let session = 0;               // crește la fiecare start/stop (vezi start())
  let callbacks = null;          // { onState, onResult, onError }
  let stream = null, audioContext = null, source = null, processor = null;

  let inSpeech = false;          // suntem în mijlocul unui segment?
  let segment = [];              // bucățile segmentului curent
  let preRoll = [];              // ultimele bucăți dinaintea vorbirii
  let silenceMs = 0, speechMs = 0;
  let noiseLevel = 0.005;        // estimarea zgomotului de fond (se actualizează)

  let busy = false;              // așteptăm răspunsul serverului
  let muted = false;             // utilizatorul a oprit ascultarea
  let ttsUntil = 0;              // până când ignorăm microfonul după text-to-speech
  let currentState = "off";

  // ------------------------------------------------------------------
  // Pornire / oprire
  // ------------------------------------------------------------------

  async function start(newCallbacks) {
    stop();
    const mySession = ++session;
    callbacks = newCallbacks;
    setState("processing", "Starting mic…");

    let micStream;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,   // reduce sunetul propriu (alarma, vocea aplicației)
          noiseSuppression: false,  // filtrarea zgomotului o facem noi, în Python
          autoGainControl: true,
        },
      });
    } catch (error) {
      if (mySession === session) setState("error", "Mic blocked");
      return;
    }

    // Dacă între timp utilizatorul a ieșit din pagină, renunțăm
    if (mySession !== session) {
      micStream.getTracks().forEach((t) => t.stop());
      return;
    }

    stream = micStream;
    audioContext = new AudioContext();
    source = audioContext.createMediaStreamSource(stream);

    // ScriptProcessorNode: cea mai simplă metodă de a primi eșantioanele în JS.
    // (E marcată „deprecated”, dar e suportată de toate browserele și e ușor de înțeles.)
    processor = audioContext.createScriptProcessor(BUFFER_SIZE, 1, 1);
    processor.onaudioprocess = (event) => onAudio(event.inputBuffer.getChannelData(0));
    source.connect(processor);
    processor.connect(audioContext.destination); // necesar ca să ruleze; ieșirea e liniște

    if (audioContext.state === "suspended") {
      // Browserul cere un click înainte de a porni sunetul (ex: după refresh)
      setState("paused", "Click to start listening");
    } else {
      setState("listening", "Listening");
    }
  }

  function stop() {
    session++;
    if (processor) processor.disconnect();
    if (source) source.disconnect();
    if (stream) stream.getTracks().forEach((track) => track.stop());
    if (audioContext) audioContext.close();
    processor = source = stream = audioContext = null;
    callbacks = null;
    busy = false;
    resetSegment();
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
    resetSegment();
    setState(muted ? "paused" : "listening", muted ? "Muted · click to listen" : "Listening");
  }

  // ------------------------------------------------------------------
  // Prelucrarea fiecărei bucăți de sunet
  // ------------------------------------------------------------------

  function onAudio(input) {
    if (!audioContext || muted || busy || audioContext.state !== "running") return;

    // Cât timp aplicația vorbește (text-to-speech), nu ascultăm
    // (altfel s-ar auzi pe ea însăși și ar executa comenzi).
    if (window.speechSynthesis && (speechSynthesis.speaking || speechSynthesis.pending)) {
      ttsUntil = performance.now() + TTS_COOLDOWN_MS;
    }
    if (performance.now() < ttsUntil) {
      resetSegment();
      if (currentState !== "paused") setState("paused", "Paused while reading");
      return;
    }
    if (currentState !== "listening") setState("listening", "Listening");

    // Copiem bucata (browserul refolosește același buffer)
    const chunk = new Float32Array(input);
    const chunkMs = (chunk.length / audioContext.sampleRate) * 1000;
    const level = rms(chunk);
    const threshold = Math.max(MIN_THRESHOLD, noiseLevel * NOISE_FACTOR);

    if (!inSpeech) {
      // Păstrăm ultimele ~300 ms (pre-roll)
      preRoll.push(chunk);
      while (preRoll.length * chunkMs > PRE_ROLL_MS) preRoll.shift();

      if (level > threshold) {
        // Începe vorbirea
        inSpeech = true;
        segment = preRoll;
        preRoll = [];
        speechMs = chunkMs;
        silenceMs = 0;
      } else {
        // Liniște: actualizăm lent estimarea zgomotului de fond (medie exponențială)
        noiseLevel = 0.95 * noiseLevel + 0.05 * level;
      }
      return;
    }

    // Suntem într-un segment
    segment.push(chunk);
    if (level > threshold) {
      speechMs += chunkMs;
      silenceMs = 0;
    } else {
      silenceMs += chunkMs;
    }

    const totalMs = segment.length * chunkMs;
    if (silenceMs >= END_SILENCE_MS || totalMs >= MAX_SEGMENT_MS) {
      const enoughSpeech = speechMs >= MIN_SPEECH_MS;
      const samples = concat(segment);
      const rate = audioContext.sampleRate;
      resetSegment();
      if (enoughSpeech) send(samples, rate);
    }
  }

  function resetSegment() {
    inSpeech = false;
    segment = [];
    preRoll = [];
    silenceMs = 0;
    speechMs = 0;
  }

  // ------------------------------------------------------------------
  // Trimiterea la server
  // ------------------------------------------------------------------

  // Metoda de recunoaștere: implicit Whisper. Pentru demo, adresa
  // http://localhost:8090/?method=dtw#/cook/1 folosește MFCC + DTW.
  const METHOD = new URLSearchParams(location.search).get("method") === "dtw" ? "dtw" : "whisper";

  async function send(samples, sampleRate) {
    const mySession = session;
    busy = true;
    setState("processing", "Thinking…");

    const wav = encodeWav(downsample(samples, sampleRate, TARGET_RATE), TARGET_RATE);

    // Pagina de înregistrare (#/record) vrea fișierul WAV, nu o comandă
    if (callbacks?.onSegment) {
      try {
        await callbacks.onSegment(wav);
      } finally {
        if (mySession === session) {
          busy = false;
          setState("listening", "Listening");
        }
      }
      return;
    }

    try {
      const form = new FormData();
      form.append("audio", wav, "command.wav");

      const response = await fetch(`/api/command?method=${METHOD}`, { method: "POST", body: form });
      const data = await response.json().catch(() => ({}));
      if (mySession !== session) return; // am ieșit din pagină între timp

      if (response.status === 503) {
        callbacks?.onError?.("Speech model is still loading…");
      } else if (!response.ok) {
        callbacks?.onError?.(data.error || "Server error " + response.status);
      } else {
        callbacks?.onResult?.(data);
      }
    } catch (error) {
      if (mySession === session) callbacks?.onError?.("Cannot reach the speech server");
    } finally {
      if (mySession === session) {
        busy = false;
        setState("listening", "Listening");
      }
    }
  }

  function setState(state, label) {
    currentState = state;
    callbacks?.onState?.(state, label);
  }

  // ------------------------------------------------------------------
  // Prelucrări de semnal simple
  // ------------------------------------------------------------------

  // RMS (Root Mean Square) = rădăcina din media pătratelor = „nivelul” sunetului
  function rms(samples) {
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    return Math.sqrt(sum / samples.length);
  }

  // Lipește mai multe bucăți într-un singur vector
  function concat(chunks) {
    const total = chunks.reduce((n, c) => n + c.length, 0);
    const result = new Float32Array(total);
    let offset = 0;
    for (const c of chunks) {
      result.set(c, offset);
      offset += c.length;
    }
    return result;
  }

  // Reeșantionare de la frecvența microfonului (de obicei 48 kHz) la 16 kHz.
  // Fiecare eșantion nou = media eșantioanelor vechi din intervalul lui.
  // Media acționează ca un filtru trece-jos simplu (reduce aliasing-ul).
  function downsample(samples, fromRate, toRate) {
    if (fromRate === toRate) return samples;
    const ratio = fromRate / toRate;
    const length = Math.floor(samples.length / ratio);
    const result = new Float32Array(length);
    for (let i = 0; i < length; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.min(Math.floor((i + 1) * ratio), samples.length);
      let sum = 0;
      for (let j = start; j < end; j++) sum += samples[j];
      result[i] = sum / Math.max(1, end - start);
    }
    return result;
  }

  // Construiește un fișier WAV: antet de 44 de octeți + eșantioane pe 16 biți
  function encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeText = (offset, text) => {
      for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
    };

    writeText(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true); // mărimea fișierului - 8
    writeText(8, "WAVE");
    writeText(12, "fmt ");
    view.setUint32(16, 16, true);              // mărimea blocului „fmt”
    view.setUint16(20, 1, true);               // 1 = PCM (necomprimat)
    view.setUint16(22, 1, true);               // 1 canal (mono)
    view.setUint32(24, sampleRate, true);      // eșantioane pe secundă
    view.setUint32(28, sampleRate * 2, true);  // octeți pe secundă
    view.setUint16(32, 2, true);               // octeți per eșantion
    view.setUint16(34, 16, true);              // biți per eșantion
    writeText(36, "data");
    view.setUint32(40, samples.length * 2, true);

    // Float [-1, 1] -> întreg pe 16 biți [-32768, 32767]
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([buffer], { type: "audio/wav" });
  }

  return { start, stop, toggle };
})();
