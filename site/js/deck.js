// Practice tab: the lesson's decks, then one card at a time.
// Where you are in a deck (3/8) lives only in this module's memory: nothing is saved.
// Opening a deck pushes a history entry on the same URL, so the phone's back gesture returns to the list.
import * as player from "./player.js";
import { esc, marks } from "./lesson.js";

const GROUPS = [
  { kinds: ["pair", "word", "phrase"], title: "단어와 구" },
  { kinds: ["sentence"], title: "문장" },
  { kinds: ["reading"], title: "짧은 글" },
];
const PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.2v13.6a.8.8 0 0 0 1.2.7l10.6-6.8a.8.8 0 0 0 0-1.4L9.2 4.5A.8.8 0 0 0 8 5.2z" fill="currentColor"/></svg>';
const STOP = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6.5" y="6.5" width="11" height="11" rx="1.6" fill="currentColor"/></svg>';
const CHEV = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const LEFT = CHEV("M14.5 6 8.5 12l6 6");
const RIGHT = CHEV("M9.5 6l6 6-6 6");

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const places = new Map(); // "lesson/deck" -> card index, memory only

let S = null; // {view, lesson, deck, i} while a deck is open
let lastLesson = null;

/* ---------- deck list ---------- */

function listHTML(lesson) {
  const groups = GROUPS.map((g) => {
    const decks = lesson.decks.filter((d) => g.kinds.includes(d.kind) && d.cards.length);
    if (!decks.length) return "";
    const rows = decks.map((d) => {
      const at = places.get(`${lesson.key}/${d.id}`);
      const n = d.cards.length;
      const prog = at ? `<span class="dl-at">${Math.min(at + 1, n)}<span>/</span></span>` : "";
      return `<li><button type="button" class="dl-row" data-open="${esc(d.id)}">` +
        `<span class="dl-text"><span class="dl-title">${esc(d.title)}</span>` +
        (d.goal ? `<span class="dl-goal">${d.goal}</span>` : "") + `</span>` +
        `<span class="dl-count">${prog}${n}</span>` +
        `<span class="dl-go" aria-hidden="true">${RIGHT}</span></button></li>`;
    }).join("");
    return `<section class="dl-group"><h2 class="dl-head">${g.title}</h2><ol class="deck-list">${rows}</ol></section>`;
  }).join("");
  return `<article class="practice" data-lesson="${esc(lesson.key)}">` +
    `<header class="lesson-head"><p class="lesson-label">${esc(lesson.label)}</p><h1 class="lesson-title">${esc(lesson.title)}</h1></header>` +
    `<div class="decks">${groups}</div></article>`;
}

export function renderPractice(view, lesson) {
  lastLesson = lesson;
  const st = history.state;
  const deck = st && st.studioLesson === lesson.key ? lesson.decks.find((d) => d.id === st.studioDeck) : null;
  if (deck) openDeck(view, lesson, deck);
  else showList(view, lesson);
}

function showList(view, lesson, focusId) {
  S = null;
  player.stop();
  view.innerHTML = listHTML(lesson);
  view.onclick = (e) => {
    const b = e.target.closest("[data-open]");
    if (!b) return;
    const deck = lesson.decks.find((d) => d.id === b.dataset.open);
    if (!deck) return;
    history.pushState({ studioLesson: lesson.key, studioDeck: deck.id }, "", location.href);
    openDeck(view, lesson, deck);
    window.scrollTo(0, 0);
  };
  if (focusId) {
    const row = view.querySelector(`[data-open="${CSS.escape(focusId)}"]`);
    if (row) { row.scrollIntoView({ block: "center" }); row.focus({ preventScroll: true }); }
  }
}

/* ---------- one card ---------- */

function beatsHTML(words, beats) {
  // beats has one mark per syllable; split it across the words so each word keeps its own group.
  const chars = [...beats];
  let k = 0;
  const groups = words.map((w) => {
    const mine = chars.slice(k, k + w.syllables);
    k += w.syllables;
    const dots = mine.map((c) => `<span class="bt ${c === "●" ? "s" : "w"}"></span>`).join("");
    return `<span class="bw">${dots}</span>` + (w.pause ? '<span class="bp">|</span>' : "");
  }).join("");
  const said = chars.map((c) => (c === "●" ? "강" : "약")).join(" ");
  return `<span class="beats" role="img" aria-label="박자 ${said}">${groups}</span>`;
}

function markedHTML(m) {
  return `<div class="mk-block">` +
    `<p class="mk-text">${marks(esc(m.marked))}</p>` +
    `<p class="mk-beats">${beatsHTML(m.words, m.beats)}<span class="mk-tune" aria-label="${m.tune === "↗" ? "올림" : "내림"}">${esc(m.tune || "↘")}</span></p>` +
    `</div>`;
}

function sizeClass(plain) {
  const n = plain.length;
  return n <= 14 ? "len-s" : n <= 34 ? "len-m" : n <= 64 ? "len-l" : "len-xl";
}

function frontHTML(c) {
  if (c.type === "pair" && c.parts && c.parts.length === 2) {
    const side = (p, i) => `<div class="fc-side">` +
      `<span class="fc-ab" aria-hidden="true">${i ? "B" : "A"}</span>` +
      `<span class="fc-word" lang="en">${esc(p.plain)}</span>` +
      (c.labels && c.labels[i] ? `<span class="fc-lab">${esc(c.labels[i])}</span>` : "") + `</div>`;
    return `<div class="fc-pair">${side(c.parts[0], 0)}${side(c.parts[1], 1)}</div>`;
  }
  return `<p class="fc-plain ${sizeClass(c.plain)}" lang="en">${esc(c.plain)}</p>`;
}

function backHTML(c) {
  if (c.type === "pair" && c.parts && c.parts.length === 2) {
    return `<div class="fc-pair mk-pair">${c.parts.map((p) => markedHTML({ ...p, tune: c.tune })).join("")}</div>`;
  }
  return markedHTML(c);
}

function playIds(c) {
  const ids = c.tts || [];
  return c.type === "pair" && ids.length === 2 ? [ids[0], ids[1], ids[0]] : ids;
}

function cardHTML(deck, i) {
  const c = deck.cards[i];
  const pair = c.type === "pair";
  return `<div class="fc-top"><span class="fc-n">${i + 1}</span>${pair ? '<span class="fc-order">A – B – A</span>' : ""}</div>` +
    `<div class="fc-front">${frontHTML(c)}</div>` +
    `<div class="fc-back" id="fc-back" hidden>${backHTML(c)}</div>` +
    `<div class="fc-acts">` +
    `<button type="button" class="fc-play" data-tts="${esc(playIds(c).join(" "))}" aria-pressed="false" aria-label="모범 발음 듣기" disabled>` +
    `<span class="ic-play">${PLAY}</span><span class="ic-stop">${STOP}</span></button>` +
    `<button type="button" class="fc-reveal" aria-expanded="false" aria-controls="fc-back">강세 보기</button>` +
    `</div>`;
}

function endHTML(lesson, deck) {
  const k = lesson.decks.indexOf(deck);
  const next = lesson.decks.slice(k + 1).find((d) => d.cards.length);
  return `<div class="fc-end">` +
    `<p class="fc-end-n">${deck.cards.length}<span>장</span></p>` +
    `<p class="fc-end-t">${esc(deck.title)}</p>` +
    `<div class="fc-end-acts">` +
    `<button type="button" class="btn" data-act="restart">처음부터</button>` +
    (next ? `<button type="button" class="btn primary" data-act="next-deck" data-deck="${esc(next.id)}">다음 덱<span class="fc-end-next">${esc(next.title)}</span></button>` : "") +
    `<button type="button" class="btn ghost" data-act="list">덱 목록</button>` +
    `</div></div>`;
}

function tipHTML(deck) {
  const parts = [deck.goal, deck.focus, deck.note, deck.check].filter(Boolean);
  if (!parts.length) return "";
  return `<details class="dv-tip"><summary><span>덱 안내</span></summary><div class="dv-tip-body">${parts.map((p) => `<p>${p}</p>`).join("")}</div></details>`;
}

function deckHTML(lesson, deck) {
  return `<article class="practice deckview" data-lesson="${esc(lesson.key)}">` +
    `<header class="dv-head">` +
    `<button type="button" class="dv-back" data-act="list" aria-label="덱 목록으로">${LEFT}<span>덱</span></button>` +
    `<h1 class="dv-title">${esc(deck.title)}</h1>` +
    `<p class="dv-count" aria-live="polite" aria-atomic="true"></p>` +
    `</header>` +
    `<div class="dv-meter" aria-hidden="true"><span></span></div>` +
    tipHTML(deck) +
    `<div class="dv-stage"><section class="fc" aria-roledescription="카드"></section></div>` +
    `<nav class="dv-bar" aria-label="카드 넘기기"><div class="dv-bar-in">` +
    `<button type="button" class="dv-nav" data-act="prev" aria-keyshortcuts="ArrowLeft" title="이전 (←)">${LEFT}<span>이전</span></button>` +
    `<button type="button" class="dv-play" data-act="play" aria-keyshortcuts="Space" title="재생 (Space)" aria-label="모범 발음 듣기" aria-pressed="false" disabled>` +
    `<span class="ic-play">${PLAY}</span><span class="ic-stop">${STOP}</span></button>` +
    `<button type="button" class="dv-nav" data-act="next" aria-keyshortcuts="ArrowRight" title="다음 (→)"><span>다음</span>${RIGHT}</button>` +
    `</div></nav></article>`;
}

function openDeck(view, lesson, deck) {
  player.stop();
  view.innerHTML = deckHTML(lesson, deck);
  const at = places.get(`${lesson.key}/${deck.id}`) || 0;
  S = { view, lesson, deck, i: Math.min(at, deck.cards.length - 1), card: view.querySelector(".fc"), anim: 0 };
  view.onclick = onClick;
  bindSwipe(view.querySelector(".dv-stage"));
  watchPlay();
  paint();
}

/** Fill the card for S.i (S.i === cards.length is the end panel) and update the counter and bar. */
function paint() {
  paintCard();
  paintChrome();
}

function paintCard() {
  const { deck, card } = S;
  const n = deck.cards.length;
  const end = S.i >= n;
  card.classList.toggle("is-end", end);
  card.setAttribute("aria-label", end ? "덱 끝" : `${S.i + 1} / ${n}`);
  card.innerHTML = end ? endHTML(S.lesson, deck) : cardHTML(deck, S.i);
  card.dataset.type = end ? "end" : deck.cards[S.i].type;
  S.shown = S.i;
  player.refresh(card);
  syncBar();
}

function paintChrome() {
  const n = S.deck.cards.length;
  const end = S.i >= n;
  if (!end) places.set(`${S.lesson.key}/${S.deck.id}`, S.i);
  const shown = Math.min(S.i + 1, n);
  S.view.querySelector(".dv-count").innerHTML = `<b>${shown}</b><span> / ${n}</span>`;
  S.view.querySelector(".dv-meter span").style.transform = `scaleX(${end ? 1 : shown / n})`;
  S.view.querySelector('[data-act="prev"]').disabled = S.i === 0;
  S.view.querySelector('[data-act="next"]').disabled = end;
}

function syncBar() {
  if (!S) return;
  const src = S.card.querySelector(".fc-play");
  const bar = S.view.querySelector(".dv-play");
  bar.disabled = !src || src.disabled;
  const on = !!src && src.getAttribute("aria-pressed") === "true";
  bar.setAttribute("aria-pressed", on ? "true" : "false");
  bar.classList.toggle("is-playing", on);
}

let observer = null;
function watchPlay() {
  if (observer) observer.disconnect();
  observer = new MutationObserver(syncBar);
  observer.observe(S.card, { subtree: true, attributes: true, attributeFilter: ["aria-pressed", "disabled"] });
}

/** Move by d cards. dx: where a dragged card was let go (px), so it leaves from there. */
function step(d, dx = 0) {
  if (!S) return false;
  const n = S.deck.cards.length;
  const to = S.i + d;
  if (to < 0 || to > n) { bump(d); return false; }
  player.stop();
  S.i = to;
  const card = S.card;
  const t = ++S.anim;
  card.getAnimations().forEach((a) => a.cancel());
  if (reduced() || !card.animate) {
    card.style.transform = "";
    paint();
    return true;
  }
  const w = Math.min(card.offsetWidth || 320, 480);
  const out = card.animate(
    [{ transform: `translateX(${dx}px)`, opacity: 1 }, { transform: `translateX(${-d * w * 0.6}px) rotate(${-d * 2}deg)`, opacity: 0 }],
    { duration: dx ? 140 : 110, easing: "cubic-bezier(.4,0,1,1)" });
  card.style.transform = "";
  paintChrome(); // the counter and buttons change at once; the card face changes once the old one has left
  out.onfinish = () => {
    if (!S || t !== S.anim) return;
    paintCard();
    card.animate(
      [{ transform: `translateX(${d * 46}px)`, opacity: 0 }, { transform: "none", opacity: 1 }],
      { duration: 220, easing: "cubic-bezier(.2,.8,.2,1)" });
  };
  return true;
}

function bump(d) {
  const card = S.card;
  if (reduced() || !card.animate) return;
  card.animate([{ transform: "none" }, { transform: `translateX(${-d * 14}px)` }, { transform: "none" }],
    { duration: 220, easing: "ease-out" });
}

function toggleBack() {
  const back = S.card.querySelector(".fc-back");
  const btn = S.card.querySelector(".fc-reveal");
  if (!back || !btn) return;
  const open = back.hidden;
  back.hidden = !open;
  btn.setAttribute("aria-expanded", open ? "true" : "false");
  btn.textContent = open ? "강세 숨기기" : "강세 보기";
}

function playCard() {
  if (S && S.shown !== S.i) { // still sliding: show the card that is due before playing it
    S.anim++;
    S.card.getAnimations().forEach((a) => a.cancel());
    paintCard();
  }
  const src = S && S.card.querySelector(".fc-play");
  if (src && !src.disabled) src.click(); // a real click inside the gesture: player.js starts audio from it (iOS)
}

function backToList() {
  if (!S) return;
  const { view, lesson, deck } = S;
  if (history.state && history.state.studioDeck) history.back(); // popstate repaints the list
  else showList(view, lesson, deck.id);
}

function onClick(e) {
  if (!S) return;
  const t = e.target.closest("[data-act], .fc-reveal");
  if (!t) return;
  if (t.classList.contains("fc-reveal")) { toggleBack(); return; }
  switch (t.dataset.act) {
    case "prev": step(-1); break;
    case "next": step(1); break;
    case "play": playCard(); break;
    case "list": backToList(); break;
    case "restart": S.i = -1; step(1); break;
    case "next-deck": {
      const deck = S.lesson.decks.find((d) => d.id === t.dataset.deck);
      if (!deck) break;
      history.replaceState({ studioLesson: S.lesson.key, studioDeck: deck.id }, "", location.href);
      openDeck(S.view, S.lesson, deck);
      window.scrollTo(0, 0);
      break;
    }
  }
}

/* ---------- swipe (pointer events, no library) ---------- */

let suppressClick = false;

function bindSwipe(stage) {
  let p = null; // {id, x, y, t, dx, drag}
  const card = () => S && S.card;

  stage.addEventListener("pointerdown", (e) => {
    if (!S || (e.pointerType === "mouse" && e.button !== 0)) return;
    p = { id: e.pointerId, x: e.clientX, y: e.clientY, t: performance.now(), dx: 0, drag: false };
  });
  stage.addEventListener("pointermove", (e) => {
    if (!p || e.pointerId !== p.id) return;
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    if (!p.drag) {
      if (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy) * 1.2) {
        p.drag = true;
        try { stage.setPointerCapture(p.id); } catch { /* pointer already gone */ }
        card().getAnimations().forEach((a) => a.cancel());
        card().classList.add("is-dragging");
      } else if (Math.abs(dy) > 12) { p = null; return; } // a vertical scroll: let the page have it
      else return;
    }
    const n = S.deck.cards.length;
    const edge = (dx > 0 && S.i === 0) || (dx < 0 && S.i >= n);
    p.dx = edge ? dx * 0.25 : dx;
    card().style.transform = `translateX(${p.dx}px) rotate(${p.dx / 40}deg)`;
    e.preventDefault();
  });
  const end = (e, cancelled) => {
    if (!p || e.pointerId !== p.id) return;
    const { drag, dx, t } = p;
    p = null;
    if (!drag) return;
    const c = card();
    c.classList.remove("is-dragging");
    suppressClick = true;
    setTimeout(() => { suppressClick = false; }, 0);
    const v = Math.abs(dx) / Math.max(1, performance.now() - t); // px per ms
    const far = Math.abs(dx) > Math.min(90, c.offsetWidth * 0.22) || (v > 0.45 && Math.abs(dx) > 30);
    if (!cancelled && far && step(dx < 0 ? 1 : -1, dx)) return;
    c.style.transform = "";
    if (!reduced() && c.animate) {
      c.animate([{ transform: `translateX(${dx}px) rotate(${dx / 40}deg)` }, { transform: "none" }],
        { duration: 200, easing: "cubic-bezier(.2,.8,.2,1)" });
    }
  };
  stage.addEventListener("pointerup", (e) => end(e, false));
  stage.addEventListener("pointercancel", (e) => end(e, true));
  // A drag that ends over a button must not press it.
  stage.addEventListener("click", (e) => {
    if (suppressClick) { e.stopPropagation(); e.preventDefault(); suppressClick = false; }
  }, true);
}

/* ---------- keyboard (PC) ---------- */

document.addEventListener("keydown", (e) => {
  if (!S || !S.view.contains(S.card) || e.altKey || e.ctrlKey || e.metaKey) return;
  const tag = (e.target && e.target.tagName) || "";
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag) || (e.target && e.target.isContentEditable)) return;
  switch (e.key) {
    case "ArrowRight": e.preventDefault(); step(1); break;
    case "ArrowLeft": e.preventDefault(); step(-1); break;
    case " ": case "Spacebar":
      e.preventDefault();
      if (!e.repeat) playCard();
      break;
    case "Escape":
      if (document.querySelector(".dv-tip[open]")) return;
      e.preventDefault(); backToList(); break;
  }
});
// Space on a focused button would also press it on keyup; the keydown above already played.
document.addEventListener("keyup", (e) => {
  if (S && (e.key === " " || e.key === "Spacebar") && e.target && e.target.tagName === "BUTTON" && S.view.contains(e.target)) e.preventDefault();
});

/* ---------- back gesture ---------- */

window.addEventListener("popstate", () => {
  const view = document.getElementById("view");
  const art = view && view.querySelector(".practice");
  if (!art) return;
  const key = art.dataset.lesson;
  const lesson = (S && S.lesson.key === key) ? S.lesson : cachedLesson(key);
  if (!lesson || !location.hash.endsWith("/practice")) return;
  const st = history.state;
  const deck = st && st.studioLesson === key ? lesson.decks.find((d) => d.id === st.studioDeck) : null;
  const from = S && S.deck.id;
  if (deck) openDeck(view, lesson, deck);
  else showList(view, lesson, from);
});

function cachedLesson(key) { return lastLesson && lastLesson.key === key ? lastLesson : null; }
