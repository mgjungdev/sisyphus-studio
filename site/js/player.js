// Model-voice playback shared by the lesson and practice tabs.
// Only two settings persist (localStorage): voice f|m and slow on/off. Nothing else is stored.
// One <audio> element is reused for every clip: iOS unlocks it on the first tap, so play() is always
// called synchronously inside the tap handler and later clips in a queue may follow without a tap.

const KEY_VOICE = "studio.voice";
const KEY_SLOW = "studio.slow";

function readPref(k, fallback) {
  try { return localStorage.getItem(k) ?? fallback; } catch { return fallback; }
}
function writePref(k, v) {
  try { localStorage.setItem(k, v); } catch { /* private mode: keep it for this visit only */ }
}

const prefs = {
  voice: readPref(KEY_VOICE, "f") === "m" ? "m" : "f",
  slow: readPref(KEY_SLOW, "0") === "1",
};

const manifests = new Map(); // lesson key -> Promise<Set<"id|v|s">>
const listeners = new Set();
let audio = null;
let queue = [];
let current = null; // {btn, lesson}

function speed() { return prefs.slow ? "80" : "100"; }

export function getPrefs() { return { ...prefs }; }

export function setVoice(v) {
  prefs.voice = v === "m" ? "m" : "f";
  writePref(KEY_VOICE, prefs.voice);
  changed();
}

export function setSlow(on) {
  prefs.slow = !!on;
  writePref(KEY_SLOW, prefs.slow ? "1" : "0");
  changed();
}

export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

function changed() {
  stop();
  listeners.forEach((fn) => fn(getPrefs()));
  refresh();
}

/** Load the lesson's audio manifest once; a missing manifest means no clips (buttons stay disabled). */
export function load(lesson) {
  if (!manifests.has(lesson)) {
    manifests.set(lesson, fetch(`audio/${lesson}/manifest.json`)
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({}))
      .then((m) => new Set(Object.keys(m))));
  }
  return manifests.get(lesson);
}

const ready = new Map(); // lesson -> Set, filled once load() resolves
export async function prepare(lesson) {
  const set = await load(lesson);
  ready.set(lesson, set);
  return set;
}

export function has(lesson, id) {
  const set = ready.get(lesson);
  return !!set && set.has(`${id}|${prefs.voice}|${speed()}`);
}

function url(lesson, id) {
  return `audio/${lesson}/${id}.${prefs.voice}.${speed()}.m4a`;
}

/** Enable or disable every [data-tts] control under root for the current voice and speed. */
export function refresh(root = document) {
  root.querySelectorAll("[data-tts]").forEach((el) => {
    const lesson = el.closest("[data-lesson]")?.dataset.lesson;
    const ids = el.dataset.tts.split(" ");
    const ok = !!lesson && ids.every((id) => has(lesson, id));
    el.disabled = !ok;
    el.classList.toggle("no-audio", !ok);
  });
}

function element() {
  if (!audio) {
    audio = new Audio();
    audio.preload = "auto";
    audio.setAttribute("playsinline", "");
    audio.addEventListener("ended", next);
    audio.addEventListener("error", () => { if (current) { queue = []; finish(); } });
  }
  return audio;
}

function mark(btn, on) {
  if (!btn) return;
  btn.classList.toggle("is-playing", on);
  btn.setAttribute("aria-pressed", on ? "true" : "false");
}

let token = 0;   // bumps on every clip, so a late rejection from an interrupted clip is ignored
let watchdog = 0;

function finish() {
  clearTimeout(watchdog);
  if (current) mark(current.btn, false);
  current = null;
}

function next() {
  clearTimeout(watchdog);
  if (!queue.length) { finish(); return; }
  const id = queue.shift();
  const a = element();
  const t = ++token;
  a.src = url(current.lesson, id);
  const p = a.play();
  if (p && p.catch) p.catch(() => { if (t === token) { queue = []; finish(); } });
  // A clip that never starts (stalled network, no decoder) must not leave the control lit.
  watchdog = setTimeout(() => { if (t === token && a.paused) { queue = []; finish(); } }, 6000);
}

/** Play ids in order (A–B–A for pairs). Call from inside the tap handler. A second tap on the same control stops it. */
export function play(lesson, ids, btn) {
  const same = current && current.btn === btn;
  stop();
  if (same) return;
  ids = (Array.isArray(ids) ? ids : [ids]).filter((id) => has(lesson, id));
  if (!ids.length) return;
  current = { btn, lesson };
  mark(btn, true);
  queue = ids.slice();
  next();
}

export function stop() {
  token++;
  queue = [];
  if (audio) { audio.pause(); }
  finish();
}

export function isPlaying() { return !!current; }

// Taps on any [data-tts] control anywhere in the app.
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-tts]");
  if (!btn || btn.disabled) return;
  const lesson = btn.closest("[data-lesson]")?.dataset.lesson;
  if (!lesson) return;
  e.preventDefault();
  play(lesson, btn.dataset.tts.split(" "), btn);
});

// Leaving the page (or switching apps on a phone) silences the clip.
document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });
