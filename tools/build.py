"""Sisyphus Studio build: content/reading/*.md (Notion enhanced markdown) -> site/data/.

Outputs
  site/data/reading/index.json     course intro blocks + lesson list
  site/data/reading/lessonNN.json  {id, title, icon, goal, blocks[], decks[]}
  site/data/tts.json               [{id, lesson, text}] every TTS target (table cells + cards)
  site/data/routes.json            hashes for tools/qa.py
  site/img/                        content/img/ (PNG as lossless WebP)
  site/sw.js                       from tools/sw.template.js: PRECACHE (app shell, icons, images, lesson data, audio
                                   manifests), VERSION (hash of those files) and AUDIO_VERSION (hash of the audio
                                   manifests). Run after tools/tts.py too, so the audio cache follows new clips.

Lesson blocks (lesson tab): h, p, callout{blocks}, table{header, rows, kind}, img, details{summary, blocks},
sentence{n, plain, marked, card, tts}, quote{html, tts[]}, ol, ul, todo.  Table cells: {html} plus "tts" (whole cell)
or "parts" [{html, tts}] (a "·" word list); 🇰🇷/Hangul cells get "kr": true and no tts.

Cards (practice tab): {id, deck, type: word|pair|phrase|sentence, plain, marked, words[{text, syllables, stress[]}],
beats ("●·" one char per syllable), tune ("↘"|"↗"), focus [word indexes in bold CAPITALS], tts [ids]};
pair cards also carry parts [{plain, marked, words, beats, tts}] (A, B).

Usage: python tools/build.py
"""
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
SITE = ROOT / "site"
DATA = SITE / "data"

HANGUL = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힯]")
IPA = re.compile(r"/[^/\s][^/]*/")
STRONG, WEAK = "●", "·"
# table columns that describe sounds instead of saying them
NO_SPEECH_COLS = {"where", "mouth", "voice", "pattern", "beat pattern", "english beats", "korean beats", "ipa",
                  "what went wrong", "position", "type", "spelling", "closest korean", "korean spelling",
                  "korean-style reading", "korean-style"}
WH = {"what", "what's", "where", "where's", "when", "who", "who's", "why", "how", "which", "whose"}

_cmu = None


def cmu() -> dict:
    global _cmu
    if _cmu is None:
        import cmudict
        _cmu = cmudict.dict()
    return _cmu


warnings: list[str] = []


def warn(msg: str) -> None:
    warnings.append(msg)


# ---------------------------------------------------------------- inline text

def unescape_md(s: str) -> str:
    return re.sub(r"\\([|*_\\`\[\]()#>~-])", r"\1", s)


def inline(s: str) -> str:
    """Notion inline markdown -> small HTML subset (strong, em, br)."""
    s = s.strip()
    parts = re.split(r"(<br\s*/?>)", s)
    out = []
    for p in parts:
        if re.fullmatch(r"<br\s*/?>", p):
            out.append("<br>")
            continue
        p = html.escape(unescape_md(p), quote=False)
        p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", p)
        out.append(p)
    return "".join(out)


def text_of(s: str) -> str:
    """Plain text of an inline markdown string."""
    s = re.sub(r"<br\s*/?>", " ", s)
    s = unescape_md(s).replace("**", "")
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- ids

def slug(s: str) -> str:
    s = s.lower().replace("’", "'").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def text_id(text: str) -> str:
    """Stable, file-safe id from text: the slug itself when short, else a truncated slug + hash."""
    sl = slug(text)
    if len(sl) <= 24 and sl:
        return sl
    words, cut = sl.split("-"), ""
    for w in words:
        if len(cut) + len(w) + 1 > 24:
            break
        cut = f"{cut}-{w}" if cut else w
    return f"{cut}-{hashlib.sha1(text.strip().lower().encode()).hexdigest()[:6]}"


# ---------------------------------------------------------------- syllables and stress

def cmu_pron(word: str):
    w = word.lower().replace("’", "'")
    prons = cmu().get(w) or cmu().get(w.strip("'"))
    return prons[0] if prons else None


def vowel_guess(word: str) -> int:
    w = word.lower()
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def cmu_syllables(word: str) -> tuple[int, list[int]]:
    """(syllables, primary-stress flags) from cmudict; vowel-count guess if missing."""
    p = cmu_pron(word)
    if not p:
        n = vowel_guess(word)
        warn(f"not in cmudict: {word!r} (guessed {n} syllables)")
        return n, [1] + [0] * (n - 1)
    vs = [ph for ph in p if ph[-1].isdigit()]
    return len(vs), [1 if v.endswith("1") else 0 for v in vs]


def is_caps(chunk: str) -> bool:
    letters = re.sub(r"[^A-Za-z]", "", chunk)
    return len(letters) >= 2 and letters.isupper()


def chunk_caps(chunk: str) -> bool:
    """A syllable chunk of a hyphenated word: 'O' in O-ver counts."""
    letters = re.sub(r"[^A-Za-z]", "", chunk)
    return bool(letters) and letters.isupper()


WORD_EDGE = re.compile(r"^[^A-Za-z']+|[^A-Za-z']+$")


def parse_marked(marked: str, isolated: bool = False) -> dict:
    """Marked text -> words[{text, syllables, stress[], marked}], beats, tune, focus.

    marked: CAPITALS = stressed, '-' = syllable boundary, '|' = pause, '‿' = link, '↘'/'↗' = tune,
    **WORD** = focus. Unhyphenated words take their syllable count from cmudict; in a sentence an
    unmarked word is weak, in isolation (word cards) it takes cmudict's primary stress.
    """
    words, focus, tunes = [], [], []
    m = unescape_md(marked)
    bold = set()
    for b in re.findall(r"\*\*(.+?)\*\*", m):
        bold.update(slug(x) for x in b.split())
    m = m.replace("**", "").replace("—", "")
    for tok in m.split():
        if tok == "|":
            if words:
                words[-1]["pause"] = True
            continue
        for arrow in "↘↗":
            if arrow in tok:
                tunes.append(arrow)
                tok = tok.replace(arrow, "")
        pieces = tok.split("‿")
        for k, piece in enumerate(pieces):
            core = WORD_EDGE.sub("", piece)
            if not core:
                continue
            chunks = [c for c in core.split("-") if c]
            text = "".join(chunks)
            if len(chunks) > 1:
                n, stress = len(chunks), [1 if chunk_caps(c) else 0 for c in chunks]
                cn, cs = cmu_syllables(text)
                if isolated and not any(stress):
                    stress = cs if cn == n else stress
            else:
                n, cs = cmu_syllables(text)
                if is_caps(text):
                    stress = cs if n > 1 else [1]
                    if n > 1 and not any(stress):
                        stress = [1] + [0] * (n - 1)
                elif isolated:
                    stress = cs if any(cs) else [1] + [0] * (n - 1)
                else:
                    stress = [0] * n
            w = {"text": text, "syllables": n, "stress": stress}
            if len(chunks) > 1 or is_caps(text):
                w["marked"] = core
            if k < len(pieces) - 1:
                w["link"] = True
            if slug(text) in bold and is_caps(text):
                focus.append(len(words))
            words.append(w)
    beats = "".join(STRONG if s else WEAK for w in words for s in w["stress"])
    end = marked.rstrip()
    if tunes:
        tune = tunes[-1]
    elif end.endswith("?"):
        first = words[0]["text"].lower() if words else ""
        tune = "↘" if first in WH else "↗"
    else:
        tune = "↘"
    return {"words": words, "beats": beats, "tune": tune, "focus": focus}


def plain_from_marked(marked: str, names: set[str]) -> str:
    """'a PEACH in a BAS-ket' -> 'a peach in a basket' (names keep their capital)."""
    m = unescape_md(marked).replace("**", "").replace("—", "")
    m = re.sub(r"\s*\|\s*", " ", m)
    m = re.sub(r"[↘↗]", "", m).replace("‿", " ")
    out = []
    for i, tok in enumerate(m.split()):
        t = tok.replace("-", "")
        core = WORD_EDGE.sub("", t)
        if is_caps(core) or ("-" in tok and any(chunk_caps(c) for c in tok.split("-"))):
            low = t.lower()
            if core.lower() in names:
                low = re.sub(r"[a-z]", lambda x: x.group(0).upper(), low, count=1)
            t = low
        out.append(t)
    s = " ".join(out)
    return re.sub(r"\s+([,.?!])", r"\1", s).strip()


def norm_words(s: str) -> list[str]:
    s = unescape_md(s).replace("**", "").replace("‿", " ").replace("—", "")
    s = re.sub(r"[|↘↗]", " ", s)
    return [w for w in (WORD_EDGE.sub("", t.replace("-", "")).lower().replace("’", "'") for t in s.split()) if w]


# ---------------------------------------------------------------- markdown parsing

def parse_attrs(s: str) -> dict:
    return dict(re.findall(r'([\w-]+)="([^"]*)"', s))


def parse_blocks(lines: list[str]) -> list[dict]:
    """Raw Notion markdown lines -> generic nodes (before lesson-specific interpretation)."""
    nodes, i = [], 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1
        if not line:
            continue
        if line.startswith("<callout"):
            attrs, body = parse_attrs(line), []
            while i < len(lines) and lines[i].strip() != "</callout>":
                body.append(lines[i][1:] if lines[i].startswith("\t") else lines[i])
                i += 1
            i += 1
            nodes.append({"t": "callout", "icon": attrs.get("icon", ""), "color": attrs.get("color", ""),
                          "blocks": parse_blocks(body)})
        elif line.startswith("<table"):
            rows, row = [], None
            while i < len(lines) and lines[i].strip() != "</table>":
                l = lines[i].strip()
                if l == "<tr>":
                    row = []
                elif l == "</tr>":
                    rows.append(row)
                elif l.startswith("<td>"):
                    row.append(re.sub(r"^<td>|</td>$", "", l))
                i += 1
            i += 1
            nodes.append({"t": "rawtable", "rows": rows, "header": 'header-row="true"' in line})
        elif line.startswith("<details"):
            summary, body = "", []
            while i < len(lines) and lines[i].strip() != "</details>":
                l = lines[i]
                if l.strip().startswith("<summary>"):
                    summary = re.sub(r"^<summary>|</summary>$", "", l.strip())
                else:
                    body.append(l[1:] if l.startswith("\t") else l)
                i += 1
            i += 1
            nodes.append({"t": "rawdetails", "summary": summary, "body": body})
        elif m := re.match(r"^(#{1,3}) (.*?)(?:\s*\{([^}]*)\})?$", line):
            n = {"t": "h", "level": len(m.group(1)), "text": text_of(m.group(2)), "html": inline(m.group(2))}
            if m.group(3):
                n["color"] = parse_attrs(m.group(3)).get("color", "")
            nodes.append(n)
        elif m := re.match(r"^!\[(.*)\]\((.*)\)$", line):
            nodes.append({"t": "img", "src": m.group(2), "alt": text_of(m.group(1))})
        elif line.startswith("> "):
            nodes.append({"t": "quote", "md": line[2:]})
        elif m := re.match(r"^- \[([ x])\] (.*)$", line):
            if nodes and nodes[-1]["t"] == "todo":
                nodes[-1]["items"].append(inline(m.group(2)))
            else:
                nodes.append({"t": "todo", "items": [inline(m.group(2))]})
        elif m := re.match(r"^(\d+)\. (.*)$", line):
            if nodes and nodes[-1]["t"] == "ol":
                nodes[-1]["items"].append(inline(m.group(2)))
            else:
                nodes.append({"t": "ol", "start": int(m.group(1)), "items": [inline(m.group(2))]})
        elif m := re.match(r"^[-*] (.*)$", line):
            if nodes and nodes[-1]["t"] == "ul":
                nodes[-1]["items"].append(inline(m.group(1)))
            else:
                nodes.append({"t": "ul", "items": [inline(m.group(1))]})
        elif m := re.match(r'^<page url="([^"]*)">(.*)</page>$', line):
            nodes.append({"t": "page", "url": m.group(1), "title": text_of(m.group(2))})
        else:
            nodes.append({"t": "p", "md": line})
    return nodes


# ---------------------------------------------------------------- lesson builder

class Lesson:
    def __init__(self, path: Path, names: set[str]):
        self.path = path
        m = re.search(r"(\d+)", path.stem)
        self.num = m.group(1) if m else path.stem
        self.key = f"lesson{self.num}"
        self.names = names
        self.tts: dict[str, str] = {}
        self.decks: list[dict] = []

    # --- tts
    def say(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        tid = text_id(text)
        old = self.tts.get(tid)
        if old is not None and old.lower().strip(".,!?") != text.lower().strip(".,!?"):
            tid = f"{tid}-{hashlib.sha1(text.encode()).hexdigest()[:4]}"
        elif old is not None and len(text) > len(old):
            self.tts[tid] = text  # same words: keep the punctuated sentence for natural prosody
        self.tts.setdefault(tid, text)
        return tid

    # --- cells
    def speakable(self, cell_md: str) -> str | None:
        """English word/phrase in a table cell -> text to say, or None."""
        t = text_of(cell_md)
        if not t or HANGUL.search(t):
            return None
        if any(" " in x.strip("/") for x in IPA.findall(t)):  # /p t k/: a list of sounds, not a word
            return None
        t = IPA.sub("", t)
        t = re.sub(r"\([^)]*\)", "", t)
        t = re.sub(r'\s*/\s*"[^"]*"', "", t)  # tree / "sree"
        t = re.sub(r"[×?]", "", t).strip(" .,")
        if not t or re.fullmatch(r"[\d–\-\s]+", t) or len(t.split()) > 8 or not re.search(r"[A-Za-z]", t):
            return None
        return plain_from_marked(t, self.names)

    def cell(self, md: str, col: str, kr_col: bool, clap_tts: str | None = None) -> dict:
        c = {"html": inline(md)}
        if kr_col or HANGUL.search(text_of(md)):
            if HANGUL.search(text_of(md)):
                c["kr"] = True
            return c
        if clap_tts:
            c["tts"] = clap_tts
            return c
        if col in NO_SPEECH_COLS:
            return c
        if " · " in text_of(md):
            parts = []
            for p in text_of(md).split(" · "):
                part = {"html": html.escape(p, quote=False)}
                if (s := self.speakable(p)):
                    part["tts"] = self.say(s)
                parts.append(part)
            return {"html": c["html"], "parts": parts}
        if (s := self.speakable(md)):
            c["tts"] = self.say(s)
        return c

    def table(self, node: dict) -> dict:
        rows = node["rows"]
        head = rows[0] if node["header"] else []
        body = rows[1:] if node["header"] else rows
        cols = [text_of(h).lower().split(" (")[0].strip() for h in head]
        kr = ["🇰🇷" in h for h in head]
        clap = bool(cols) and all(c.startswith("clap") for c in cols)
        out_rows = []
        for r in body:
            clap_tts = None
            if clap:
                line = plain_from_marked(" ".join(text_of(x) for x in r), self.names)
                clap_tts = self.say(line[:1].upper() + line[1:])
            out_rows.append([self.cell(x, cols[j] if j < len(cols) else "", j < len(kr) and kr[j], clap_tts)
                             for j, x in enumerate(r)])
        t = {"t": "table", "header": [{"html": inline(h), **({"kr": True} if "🇰🇷" in h else {})} for h in head],
             "rows": out_rows}
        if clap:
            t["kind"] = "clap"
        return t

    # --- decks
    def word_group_deck(self, title: str, node: dict) -> dict | None:
        rows = node["rows"]
        head, body = rows[0], rows[1:]
        cols = [text_of(h).lower().split(" (")[0].strip() for h in head]
        did = "wg-" + slug(title.split(".")[0])
        cards: list[dict] = []
        if is_pair_table(rows):
            labels = [text_of(h) for h in head[:2]]
            for r in body:
                a, b = (pair_word(x) for x in r[:2])
                pa, pb = (self.word_part(x) for x in (a, b))
                cards.append({"id": f"{did}.{slug(pa['plain'])}-{slug(pb['plain'])}", "deck": did, "type": "pair",
                              "plain": f"{pa['plain']} · {pb['plain']}", "marked": f"{pa['marked']} · {pb['marked']}",
                              "words": pa["words"] + pb["words"], "beats": pa["beats"] + pb["beats"],
                              "tune": "↘", "focus": [], "tts": [pa["tts"], pb["tts"]], "parts": [pa, pb],
                              "labels": labels})
            kind = "pair"
        elif "beat pattern" in cols:
            for r in body:
                marked, pattern = text_of(r[0]), re.sub(r"\s+", "", text_of(r[1]))
                info = parse_marked(marked)
                n = sum(w["syllables"] for w in info["words"])
                if len(pattern) == n:
                    if pattern != info["beats"]:
                        warn(f"{self.key} {marked!r}: CAPITALS give {info['beats']}, pattern column {pattern}; using the column")
                    flags = [1 if ch == STRONG else 0 for ch in pattern]
                    k = 0
                    for w in info["words"]:
                        w["stress"] = flags[k:k + w["syllables"]]
                        k += w["syllables"]
                    info["beats"] = pattern
                else:
                    warn(f"{self.key} {marked!r}: {n} syllables but pattern {pattern} has {len(pattern)}")
                plain = plain_from_marked(marked, self.names)
                cards.append({"id": f"{did}.{text_id(plain)}", "deck": did, "type": "phrase", "plain": plain,
                              "marked": marked, **info, "tts": [self.say(plain)]})
            kind = "phrase"
        else:
            # word lists: every "·" item of every English column (not 🇰🇷, not description columns)
            for r in body:
                for j, x in enumerate(r):
                    col = cols[j] if j < len(cols) else ""
                    if "🇰🇷" in head[j] or col in NO_SPEECH_COLS or HANGUL.search(text_of(x)):
                        continue
                    if j == 0 and len(r) > 1 and cols[0] in ("spelling", "position", "type", "pattern"):
                        continue
                    for item in text_of(x).split(" · "):
                        if not self.speakable(item):
                            continue
                        p = self.word_part(item)
                        cards.append({"id": f"{did}.{slug(p['plain'])}", "deck": did, "type": "word",
                                      "plain": p["plain"], "marked": p["marked"], "words": p["words"],
                                      "beats": p["beats"], "tune": "↘", "focus": [], "tts": [p["tts"]]})
            kind = "word"
        if not cards:
            return None
        return {"id": did, "title": title, "kind": kind, "cards": cards}

    def word_part(self, item: str) -> dict:
        marked = re.sub(r"\s*\([^)]*\)", "", IPA.sub("", item)).strip()
        marked = re.sub(r'\s*/\s*"[^"]*"', "", marked).strip()
        info = parse_marked(marked, isolated=True)
        plain = plain_from_marked(marked, self.names)
        return {"plain": plain, "marked": marked, "words": info["words"], "beats": info["beats"],
                "tts": self.say(plain)}

    def sentence_card(self, did: str, plain: str, marked: str) -> dict:
        info = parse_marked(marked)
        if norm_words(plain) != norm_words(marked):
            warn(f"{self.key} words differ: {plain!r} vs {marked!r}")
        tid = self.say(plain)
        return {"id": f"{did}.{text_id(plain)}", "deck": did, "type": "sentence", "plain": plain, "marked": marked,
                **info, "tts": [tid]}

    # --- whole lesson
    def build(self) -> dict:
        lines = self.path.read_text(encoding="utf-8").splitlines()
        title_line = lines[0].strip()
        m = re.match(r"^(Lesson|Reference)\s+(\d+)\s*·\s*(.*)$", title_line)
        title = m.group(3) if m else title_line
        nodes = parse_blocks(lines[1:])
        blocks, goal = [], None
        h2 = h3 = ""
        deck: dict | None = None  # current read-aloud deck
        notes: list[str] = []  # paragraphs under the current H2/H3, for word-group deck notes
        h2_notes: list[str] = []
        for node in nodes:
            t = node["t"]
            if t == "p":
                ph = inline(node["md"])
                if deck is not None:
                    key = "check" if re.match(r"^\*\*(Self-check|Reading focus):\*\*", node["md"]) else "note"
                    deck[key] = f"{deck[key]}<br>{ph}" if deck.get(key) else ph
                elif is_word_groups(h2):
                    (notes if h3 else h2_notes).append(ph)
            if t == "h":
                notes = []
                if node["level"] <= 2:
                    h2_notes = []
                    h2, h3, deck = node["text"], "", None
                else:
                    h3, deck = node["text"], None
                    if is_read_aloud(h2) and is_read_deck(h3):
                        deck = self.read_deck(h3)
                blocks.append(node)
                continue
            if t == "callout":
                inner = self.render(node["blocks"])
                if not inner:
                    continue
                if goal is None and node["icon"] == "🎯" and not blocks:
                    goal = inner
                    continue
                if deck is not None and node["icon"] == "🎯":
                    for b in node["blocks"]:
                        if b["t"] == "p":
                            mm = re.match(r"^\*\*(Goal|Focus):\*\*\s*(.*)$", b["md"])
                            if mm:
                                deck[mm.group(1).lower()] = inline(mm.group(2))
                blocks.append({"t": "callout", "icon": node["icon"], "color": node["color"],
                               "kind": callout_kind(node["icon"]), "blocks": inner})
                continue
            if t == "rawtable":
                blk = self.table(node)
                if is_word_groups(h2) and h3:
                    d = self.word_group_deck(h3, node)
                    if d:
                        if notes or h2_notes:
                            d["note"] = "<br>".join(notes or h2_notes)
                        self.decks.append(d)
                        blk["deck"] = d["id"]
                        if d["kind"] == "pair":
                            blk["kind"] = "pair"
                        elif d["kind"] == "phrase":
                            blk["kind"] = "phrase"
                blocks.append(blk)
                continue
            if t == "rawdetails":
                sm = re.match(r"^(\d+)\)\s*(.*)$", node["summary"])
                body_text = " ".join(l.strip() for l in node["body"] if l.strip())
                if sm and deck is not None:
                    card = self.sentence_card(deck["id"], text_of(sm.group(2)), text_of(body_text))
                    deck["cards"].append(card)
                    blocks.append({"t": "sentence", "n": int(sm.group(1)), "plain": card["plain"],
                                   "marked": card["marked"], "card": card["id"], "tts": card["tts"][0]})
                    continue
                if deck is not None and deck.get("passage"):
                    marked = text_of(body_text)
                    sents = split_sentences(deck.pop("passage"))
                    msegs = split_marked(marked)
                    if len(sents) != len(msegs):
                        sys.exit(f"{self.key}: passage has {len(sents)} sentences but marked version {len(msegs)}")
                    for s, mk in zip(sents, msegs):
                        deck["cards"].append(self.sentence_card(deck["id"], s, mk))
                    qb = next(b for b in reversed(blocks) if b["t"] == "quote")
                    qb["tts"] = [c["tts"][0] for c in deck["cards"]]
                    qb["cards"] = [c["id"] for c in deck["cards"]]
                blocks.append({"t": "details", "summary": inline(node["summary"]),
                               "blocks": self.render(parse_blocks(node["body"]))})
                continue
            if t == "quote" and deck is not None:
                deck["passage"] = text_of(node["md"])
            blocks.extend(self.render([node]))
        for d in self.decks:
            d.pop("passage", None)
        self.decks = [d for d in self.decks if d["cards"]]
        return {"id": self.num, "key": self.key, "title": title, "label": title_line.split("·")[0].strip(),
                "icon": None, "goal": goal or [], "blocks": blocks, "decks": self.decks}

    def read_deck(self, h3: str) -> dict:
        if h3.lower().startswith("warm-up"):
            did = "warmup"
        elif m := re.match(r"^PRACTICE ([A-Z])", h3):
            did = f"practice-{m.group(1).lower()}"
        else:
            did = "reading"
        d = {"id": did, "title": h3, "kind": "reading" if did == "reading" else "sentence", "cards": []}
        self.decks.append(d)
        return d

    def render(self, nodes: list[dict]) -> list[dict]:
        out = []
        for n in nodes:
            t = n["t"]
            if t == "p":
                out.append({"t": "p", "html": inline(n["md"])})
            elif t == "quote":
                out.append({"t": "quote", "html": inline(n["md"])})
            elif t == "callout":
                inner = self.render(n["blocks"])
                if inner:
                    out.append({"t": "callout", "icon": n["icon"], "color": n["color"],
                                "kind": callout_kind(n["icon"]), "blocks": inner})
            elif t == "rawtable":
                out.append(self.table(n))
            elif t == "rawdetails":
                out.append({"t": "details", "summary": inline(n["summary"]),
                            "blocks": self.render(parse_blocks(n["body"]))})
            elif t == "img":
                out.append({"t": "img", "src": web_image(n["src"]), "alt": n["alt"], **image_size(n["src"])})
            elif t == "h":
                out.append(n)
            else:
                out.append(n)
        return out


def callout_kind(icon: str) -> str:
    return {"🎯": "goal", "🗝️": "key", "🇰🇷": "kr", "💡": "note", "🎙️": "intro"}.get(icon, "note")


def is_word_groups(h2: str) -> bool:
    return "word groups" in h2.lower()


def is_read_aloud(h2: str) -> bool:
    return "read aloud" in h2.lower()


def is_read_deck(h3: str) -> bool:
    return bool(re.match(r"^(Warm-up|PRACTICE [A-Z]|Short reading)", h3))


SINGLE = re.compile(r"^[A-Za-z][A-Za-z'—-]*(\s+/[^/]+/|\s+\([^)]*\))?$")


def is_pair_table(rows: list[list[str]]) -> bool:
    """Contrast table: the first two columns hold one English word per row."""
    body = rows[1:]
    return bool(body) and len(rows[0]) >= 2 and all(
        len(r) >= 2 and all(SINGLE.match(text_of(x)) and not HANGUL.search(x) for x in r[:2]) for r in body)


def pair_word(cell: str) -> str:
    return text_of(cell)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text) if s.strip()]


def split_marked(marked: str) -> list[str]:
    segs = re.split(r"(?<=[.!?])\s*(?:\\?\|)?\s+(?=[A-Z])", marked)
    return [re.sub(r"^\|\s*|\s*\|$", "", s.strip()).strip() for s in segs if s.strip()]


def collect_names(paths: list[Path]) -> set[str]:
    """Capitalized words that are not sentence-initial in summaries and passages (Ben, Kate, Thursday...)."""
    names: set[str] = set()
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            m = re.match(r"^<summary>\d+\)\s*(.*)</summary>$", line)
            texts = [m.group(1)] if m else ([line[2:]] if line.startswith("> ") else [])
            for t in texts:
                for s in split_sentences(text_of(t)):
                    toks = s.split()
                    for w in toks[1:]:
                        core = WORD_EDGE.sub("", w)
                        core = re.sub(r"'s$", "", core)
                        if core[:1].isupper() and core != "I" and not core.startswith("I'"):
                            names.add(core.lower())
    return names


# ---------------------------------------------------------------- course

def build_course(path: Path, built: dict[str, dict]) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    title = lines[0].strip()
    nodes = parse_blocks(lines[1:])
    tmp = Lesson(path, set())
    intro, groups, group = [], [], None
    icon = ""
    for n in nodes:
        if n["t"] == "callout" and not icon:
            icon = n["icon"]
        if n["t"] == "h" and n["level"] == 2 and group is not None or (
                n["t"] == "h" and n["level"] == 2 and re.match(r"^\d+ /|Reference", n["text"])):
            group = {"title": n["text"], "lessons": []}
            groups.append(group)
            continue
        if n["t"] == "page":
            m = re.match(r"^(Lesson|Reference)\s+(\d+)\s*·\s*(.*)$", n["title"])
            if m and m.group(1) == "Lesson" and m.group(2) in built and group is not None:
                group["lessons"].append(m.group(2))
            continue
        if group is None:
            intro.extend(tmp.render([n]))
    lessons = [{"id": k, "label": v["label"], "title": v["title"], "icon": v["icon"],
                "goal": v["goal"][0]["html"] if v["goal"] else "",
                "decks": len(v["decks"]), "cards": sum(len(d["cards"]) for d in v["decks"])}
               for k, v in sorted(built.items())]
    return {"id": "reading", "title": title.split("·")[-1].strip(), "label": title, "icon": icon,
            "intro": intro, "groups": [g for g in groups if g["lessons"]], "lessons": lessons}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def web_image(src: str) -> str:
    """content/img PNGs ship as lossless WebP (half the bytes, same pixels)."""
    return src[:-4] + ".webp" if src.lower().endswith(".png") else src


def image_size(src: str) -> dict:
    """{"w", "h"} from a PNG header, so the page reserves the figure's box before the image arrives."""
    f = CONTENT / src
    head = f.read_bytes()[:24] if f.exists() else b""
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return {}
    return {"w": int.from_bytes(head[16:20], "big"), "h": int.from_bytes(head[20:24], "big")}


def copy_images() -> None:
    """content/img/ -> site/img/: PNG as lossless WebP (re-encoded only when the source is newer), others as is."""
    import subprocess
    import imageio_ffmpeg
    dst_dir = SITE / "img"
    dst_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted((CONTENT / "img").glob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() != ".png":
            shutil.copy2(f, dst_dir / f.name)
            continue
        dst = dst_dir / (f.stem + ".webp")
        if not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime:
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(f),
                            "-c:v", "libwebp", "-lossless", "1", "-compression_level", "6", str(dst)], check=True)
        (dst_dir / f.name).unlink(missing_ok=True)  # the PNG copy older builds left


SW_TEMPLATE = ROOT / "tools" / "sw.template.js"


def precache_files() -> list[str]:
    """Site-relative URLs the service worker caches on install. Clips are left out: they are cached on first play."""
    files = ["index.html", "manifest.webmanifest"]
    for pattern in ("css/*.css", "js/*.js", "img/*", "data/reading/*.json", "audio/*/manifest.json"):
        files += sorted(p.relative_to(SITE).as_posix() for p in SITE.glob(pattern) if p.is_file())
    return files


def digest(paths: list[Path], extra: bytes = b"") -> str:
    h = hashlib.sha256(extra)
    for p in paths:
        h.update(p.relative_to(SITE).as_posix().encode() + bytes(1) + p.read_bytes())
    return h.hexdigest()[:12]


def write_sw() -> int:
    files = precache_files()
    template = SW_TEMPLATE.read_text(encoding="utf-8")
    version = digest([SITE / f for f in files], template.encode())
    audio_version = digest(sorted(SITE.glob("audio/*/manifest.json")))
    sw = (template.replace("__VERSION__", version).replace("__AUDIO_VERSION__", audio_version)
          .replace("__PRECACHE__", json.dumps(["./"] + files, indent=1)))
    (SITE / "sw.js").write_bytes(sw.encode("utf-8"))
    print(f"sw.js: VERSION {version}, AUDIO_VERSION {audio_version}, {len(files) + 1} precached")
    return len(files) + 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    src = sorted((CONTENT / "reading").glob("lesson*.md"))
    names = collect_names(src)
    course_md = CONTENT / "reading" / "_course.md"
    course_icon = parse_attrs(next(l for l in course_md.read_text(encoding="utf-8").splitlines()
                                   if l.startswith("<callout"))).get("icon", "")
    built, tts = {}, []
    for p in src:
        les = Lesson(p, names)
        data = les.build()
        data["icon"] = data["icon"] or course_icon
        built[les.num] = data
        write_json(DATA / "reading" / f"{les.key}.json", data)
        tts += [{"id": k, "lesson": les.key, "text": v} for k, v in les.tts.items()]
        n_cards = sum(len(d["cards"]) for d in data["decks"])
        print(f"{les.key}: {len(data['blocks'])} blocks, {len(data['decks'])} decks, {n_cards} cards, {len(les.tts)} tts")
    write_json(DATA / "reading" / "index.json", build_course(course_md, built))
    write_json(DATA / "tts.json", tts)
    routes = ["#/"] + [f"#/reading/{k}/{tab}" for k in sorted(built) for tab in ("lesson", "practice")]
    write_json(DATA / "routes.json", routes)
    copy_images()
    print(f"tts: {len(tts)} items; routes: {len(routes)}")
    write_sw()
    for w in dict.fromkeys(warnings):
        print("warning:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
