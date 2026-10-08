// Lesson tab: renders a lesson's blocks (read-only). Tapping an English word or phrase plays the model voice.
// The checklist ticks live only on the page: nothing is saved.

const SPEAKER = '<svg class="say-ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 6h2.2L8 3.2v9.6L4.7 10H2.5z" fill="currentColor"/><path class="w1" d="M10.4 5.6a3.2 3.2 0 0 1 0 4.8" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path class="w2" d="M12.3 3.8a5.8 5.8 0 0 1 0 8.4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>';

export const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const strip = (html) => html.replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").trim();

export function slug(s) {
  return strip(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "s";
}

/** A tappable model-voice control. ids: one tts id or several played in order. */
export function say(inner, ids, cls = "") {
  const list = Array.isArray(ids) ? ids : [ids];
  return `<button type="button" class="say ${cls}" data-tts="${esc(list.join(" "))}" aria-pressed="false" disabled>` +
    `<span class="say-txt">${inner}</span>${SPEAKER}</button>`;
}

/** Marked text: CAPITAL syllables strong, | pause, ‿ link, ↘↗ tune. Works on text nodes of trusted html. */
export function marks(html) {
  return html.replace(/(<[^>]+>)|([^<]+)/g, (m, tag, text) => {
    if (tag) return tag;
    return text
      .replace(/[A-Za-z’']+/g, (w) => {
        const letters = w.replace(/[’']/g, "");
        if (letters.length < 1 || letters !== letters.toUpperCase() || /^I$/.test(letters)) return w;
        if (letters.length === 1 && letters !== "A") return w;
        return `<b class="st">${w}</b>`;
      })
      .replace(/\|/g, '<span class="mk-pause" aria-hidden="true">|</span>')
      .replace(/‿/g, '<span class="mk-link" aria-hidden="true">‿</span>')
      .replace(/([↘↗])/g, '<span class="mk-tune">$1</span>');
  });
}

function cellHTML(c) {
  if (c.parts) return `<span class="parts">${c.parts.map((p) => (p.tts ? say(p.html, p.tts, "say-chip") : `<span>${p.html}</span>`)).join("")}</span>`;
  if (c.tts) return say(c.html, c.tts, "say-cell");
  return c.html;
}

function table(b) {
  const labels = b.header.map((h) => strip(h.html));
  const n = labels.length;
  // On narrow screens each row becomes a card: short cells sit side by side, long ones take the full width.
  const wide = (c) => !!c.parts || strip(c.html).length > 26;
  const allShort = b.rows.every((r) => r.every((c) => !wide(c)));
  const mcols = allShort && n <= 3 ? n : 2;
  const head = `<thead><tr>${b.header.map((h, i) => `<th scope="col"${krCol(b, i) ? ' class="kr"' : ""}>${h.html}</th>`).join("")}</tr></thead>`;
  const body = b.rows.map((r) => {
    const tds = r.map((c, i) => {
      const cls = [c.kr ? "kr" : "", c.tts || c.parts ? "en" : "", wide(c) && mcols < n ? "wide" : ""].filter(Boolean).join(" ");
      return `<td data-label="${esc(labels[i] || "")}"${cls ? ` class="${cls}"` : ""}>${cellHTML(c)}</td>`;
    }).join("");
    return `<tr>${tds}</tr>`;
  }).join("");
  const kind = (b.kind ? ` tbl-${b.kind}` : "") + (mcols === n ? " tbl-short" : "");
  return `<div class="tbl-wrap"><table class="tbl${kind}" style="--mcols:${mcols}">${head}<tbody>${body}</tbody></table></div>`;
}

function krCol(b, i) {
  return b.rows.length && b.rows.every((r) => r[i] && r[i].kr);
}

function callout(b, ctx) {
  const kr = b.kind === "kr" || b.icon === "🇰🇷";
  const color = (b.color || "gray_bg").replace(/[^a-z_]/g, "");
  const cls = `callout co-${kr ? "kr" : color} k-${esc(b.kind || "note")}`;
  return `<aside class="${cls}"><span class="co-icon" aria-hidden="true">${esc(b.icon || "")}</span>` +
    `<div class="co-body">${render(b.blocks, ctx)}</div></aside>`;
}

function sentence(b) {
  return `<div class="sent">` +
    `<span class="sent-n">${b.n}</span>` +
    `<p class="sent-plain">${esc(b.plain)}</p>` +
    say("", b.tts, "say-round") +
    `<details class="sent-marked"><summary><span>강세 보기</span></summary><p>${marks(esc(b.marked))}</p></details>` +
    `</div>`;
}

let todoSeq = 0;
function todo(b) {
  return `<ul class="todo">${b.items.map((it) => {
    const id = `todo-${++todoSeq}`;
    return `<li><input type="checkbox" id="${id}"><label for="${id}"><span class="tick" aria-hidden="true"></span><span>${it}</span></label></li>`;
  }).join("")}</ul>`;
}

function block(b, ctx) {
  switch (b.t) {
    case "h": {
      const lvl = Math.min(Math.max(b.level || 2, 2), 4);
      const id = lvl === 2 ? ` id="${ctx.idFor(b.text)}"` : "";
      const color = b.color ? ` data-color="${esc(b.color)}"` : "";
      return `<h${lvl}${id}${color} class="h${lvl}">${b.html}</h${lvl}>`;
    }
    case "p": return `<p>${b.html}</p>`;
    case "ol": return `<ol${b.start && b.start !== 1 ? ` start="${b.start}"` : ""}>${b.items.map((i) => `<li>${i}</li>`).join("")}</ol>`;
    case "ul": return `<ul>${b.items.map((i) => `<li>${i}</li>`).join("")}</ul>`;
    case "todo": return todo(b);
    case "table": return table(b);
    case "callout": return callout(b, ctx);
    case "img": return `<figure class="fig"><img src="${esc(b.src)}" alt="${esc(b.alt || "")}"${b.w ? ` width="${b.w}" height="${b.h}"` : ""} loading="lazy" decoding="async"></figure>`;
    case "sentence": return sentence(b);
    case "quote": return `<figure class="passage"><blockquote>${b.html}</blockquote>` +
      (b.tts && b.tts.length ? `<figcaption>${say("<span>지문 듣기</span>", b.tts, "say-pill")}</figcaption>` : "") + `</figure>`;
    case "details": {
      const marked = /marked/i.test(b.summary);
      const inner = render(b.blocks, ctx);
      return `<details class="disc${marked ? " disc-marked" : ""}"><summary><span>${esc(b.summary.replace(/^▶\s*/, ""))}</span></summary>` +
        `<div class="disc-body">${marked ? marks(inner) : inner}</div></details>`;
    }
    case "hr": return "<hr>";
    default: return b.html ? `<p>${b.html}</p>` : "";
  }
}

export function render(blocks, ctx = makeCtx()) {
  return (blocks || []).map((b) => block(b, ctx)).join("");
}

export function makeCtx() {
  const used = new Set();
  return {
    toc: [],
    idFor(text) {
      let id = "s-" + slug(text), k = 2;
      while (used.has(id)) id = `s-${slug(text)}-${k++}`;
      used.add(id);
      this.toc.push({ id, text: strip(text) });
      return id;
    },
  };
}

/** The lesson page: header, goal, then the blocks; a section rail on wide screens. */
export function renderLesson(lesson) {
  const ctx = makeCtx();
  const body = render(lesson.blocks, ctx);
  const goal = Array.isArray(lesson.goal) ? render(lesson.goal, ctx) : (lesson.goal ? `<p>${lesson.goal}</p>` : "");
  const toc = ctx.toc.map((t) => {
    const m = t.text.match(/^(\d+)\s*\/\s*(.*)$/);
    return `<li><a href="#${t.id}" data-jump="${t.id}">${m ? `<span class="toc-n">${m[1]}</span>${esc(m[2])}` : esc(t.text)}</a></li>`;
  }).join("");
  return `<article class="lesson" data-lesson="${esc(lesson.key)}">` +
    `<header class="lesson-head">` +
    `<p class="lesson-label">${esc(lesson.label || "")}</p>` +
    `<h1 class="lesson-title">${esc(lesson.title)}</h1>` +
    (goal ? `<div class="goal">${goal}</div>` : "") +
    `</header>` +
    (toc ? `<nav class="toc" aria-label="이 레슨의 절"><ol>${toc}</ol></nav>` : "") +
    `<div class="prose">${body}</div>` +
    `</article>`;
}
