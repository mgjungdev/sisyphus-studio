// Hash routes: #/ course home · #/reading/NN/lesson · #/reading/NN/practice (top tabs 레슨 | 연습).
import * as player from "./player.js";
import { render, renderLesson, esc } from "./lesson.js";
import { renderPractice } from "./deck.js";

const view = document.getElementById("view");
const tabs = document.getElementById("tabs");
const voiceBar = document.getElementById("voicebar");
const cache = new Map();

function getJSON(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(path).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${path}`);
      return r.json();
    }).catch((e) => { cache.delete(path); throw e; }));
  }
  return cache.get(path);
}

const course = () => getJSON("data/reading/index.json");
const lessonData = (nn) => getJSON(`data/reading/lesson${nn}.json`);

function parse(hash) {
  const m = hash.replace(/^#/, "").match(/^\/reading\/(\d{2})\/(lesson|practice)\/?$/);
  return m ? { name: m[2], nn: m[1] } : { name: "home" };
}

/* ---------- course home ---------- */

// The course title written in the course's own reading marks: READ-ing STU-di-o, ● · ● · ·
const TITLE_WORDS = [[["READ", 1], ["ing", 0]], [["STU", 1], ["di", 0], ["o", 0]]];
function heroTitle(title) {
  if (title !== "Reading Studio") return `<h1 class="hero-title plain">${esc(title)}</h1>`;
  const words = TITLE_WORDS.map((w) => `<span class="hw">${w.map((s, i) => {
    const joiner = i < w.length - 1 ? '<span class="hy" aria-hidden="true">-</span>' : "";
    return `<span class="syl${s[1] ? " strong" : ""}"><span class="syl-t">${s[0]}${joiner}</span><span class="beat" aria-hidden="true"></span></span>`;
  }).join("")}</span>`).join("");
  return `<h1 class="hero-title" aria-label="${esc(title)}">${words}</h1>`;
}

function lessonGoal(l) {
  return String(l.goal || "").replace(/^<strong>[^<]*goal:?<\/strong>\s*/i, "");
}

function homeHTML(c) {
  const [lead, ...rest] = c.intro;
  const leadHTML = lead && lead.t === "callout" ? render(lead.blocks) : render([lead]);
  const byId = new Map(c.lessons.map((l) => [l.id, l]));
  const groups = (c.groups && c.groups.length ? c.groups : [{ title: "", lessons: c.lessons.map((l) => l.id) }]).map((g) => {
    const items = g.lessons.map((id) => byId.get(id)).filter(Boolean).map((l) => (
      `<li class="lcard">` +
      `<a class="lcard-main" href="#/reading/${l.id}/lesson">` +
      `<span class="lcard-num" aria-hidden="true">${esc(l.id)}</span>` +
      `<span class="lcard-text"><span class="lcard-label">${esc(l.label)}</span>` +
      `<span class="lcard-title">${esc(l.title)}</span>` +
      `<span class="lcard-goal">${lessonGoal(l)}</span></span></a>` +
      `<div class="lcard-acts">` +
      `<a class="btn" href="#/reading/${l.id}/lesson">레슨</a>` +
      `<a class="btn primary" href="#/reading/${l.id}/practice">연습<span class="count">${l.cards}</span></a>` +
      `</div></li>`
    )).join("");
    return `<section class="lgroup">${g.title ? `<h2 class="lgroup-title">${esc(g.title)}</h2>` : ""}<ol class="lcards">${items}</ol></section>`;
  }).join("");
  return `<div class="home">` +
    `<header class="hero">${heroTitle(c.title)}<div class="hero-lead">${leadHTML}</div></header>` +
    groups +
    `<div class="prose home-prose">${render(rest)}</div>` +
    `</div>`;
}

/* ---------- shell ---------- */

function setTabs(route) {
  const on = route.name === "lesson" || route.name === "practice";
  tabs.hidden = !on;
  voiceBar.hidden = !on;
  document.body.dataset.view = route.name;
  if (!on) return;
  tabs.dataset.on = route.name;
  tabs.querySelectorAll("a").forEach((a) => {
    a.href = `#/reading/${route.nn}/${a.dataset.tab}`;
    if (a.dataset.tab === route.name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

function syncVoiceBar() {
  const p = player.getPrefs();
  const v = document.getElementById("pref-voice");
  const s = document.getElementById("pref-slow");
  v.querySelector(".pv").textContent = p.voice === "m" ? "남" : "여";
  v.setAttribute("aria-label", p.voice === "m" ? "목소리: 남성 (눌러서 여성으로)" : "목소리: 여성 (눌러서 남성으로)");
  v.dataset.voice = p.voice;
  s.setAttribute("aria-pressed", p.slow ? "true" : "false");
}

function failHTML(msg) {
  return `<div class="empty"><p>${esc(msg)}</p><p><a class="btn" href="#/">과정 홈으로</a></p></div>`;
}

let seq = 0;
let lastKey = "";
async function go() {
  const route = parse(location.hash);
  const key = route.name === "home" ? "home" : `${route.nn}/${route.name}`;
  const n = ++seq;
  player.stop();
  setTabs(route);
  try {
    if (route.name === "home") {
      const c = await course();
      if (n !== seq) return;
      document.title = `${c.title} · Sisyphus Studio`;
      view.innerHTML = homeHTML(c);
    } else {
      const lesson = await lessonData(route.nn);
      await player.prepare(lesson.key);
      if (n !== seq) return;
      document.title = `${lesson.label} ${route.name === "lesson" ? "레슨" : "연습"} · Sisyphus Studio`;
      if (route.name === "lesson") view.innerHTML = renderLesson(lesson);
      else renderPractice(view, lesson);
      player.refresh(view);
    }
  } catch (e) {
    if (n !== seq) return;
    view.innerHTML = route.name === "home" ? failHTML("과정을 불러오지 못했습니다. 연결을 확인하고 새로고침하세요.")
      : failHTML("이 레슨을 찾을 수 없습니다.");
  }
  if (key !== lastKey) {
    window.scrollTo(0, 0);
    if (lastKey) view.focus({ preventScroll: true });
  }
  lastKey = key;
}

/* ---------- events ---------- */

document.getElementById("pref-voice").addEventListener("click", () => {
  player.setVoice(player.getPrefs().voice === "m" ? "f" : "m");
});
document.getElementById("pref-slow").addEventListener("click", () => {
  player.setSlow(!player.getPrefs().slow);
});
player.onChange(syncVoiceBar);
syncVoiceBar();

// In-page section links must not touch the route hash.
view.addEventListener("click", (e) => {
  const a = e.target.closest("[data-jump]");
  if (!a) return;
  e.preventDefault();
  const t = document.getElementById(a.dataset.jump);
  if (t) {
    t.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    t.setAttribute("tabindex", "-1");
    t.focus({ preventScroll: true });
  }
});

window.addEventListener("hashchange", go);
go();

// Offline copy of the app shell and lessons (sw.js); registered after the first screen so it never competes with it.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => { navigator.serviceWorker.register("sw.js").catch(() => {}); });
}
