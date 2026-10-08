"""Checks site/data/ (made by tools/build.py) against counts taken straight from content/reading/*.md.

- sentence <details> (summary "N) ...") = Warm-up + PRACTICE cards; passage sentences = Short reading cards
- contrast-table rows (Word groups, one word per cell in the first two columns) = pair cards
- phrase-table rows = phrase cards, and their "Beat pattern" column = card beats
- ids unique (decks, cards, tts per lesson); every tts id a card or cell uses exists; no Hangul in tts text
- every card: len(beats) = sum of word syllables, len(stress) = syllables; sentence plain/marked have the same words
- Drill "English beats" column = syllables of the English cell; images exist; routes cover every lesson tab

Usage: python tools/test_build.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "content" / "reading"
DATA = ROOT / "site" / "data"
sys.path.insert(0, str(ROOT / "tools"))
import build  # noqa: E402  (only for the drill syllable check)

HANGUL = re.compile(r"[가-힯㄰-㆏]")
errors: list[str] = []


def check(ok: bool, msg: str) -> None:
    if not ok:
        errors.append(msg)


def section(md: str, name: str) -> str:
    m = re.search(rf"^## [^\n]*{re.escape(name)}[^\n]*$(.*?)(?=^## |\Z)", md, re.M | re.S | re.I)
    return m.group(1) if m else ""


def tables(md: str) -> list[list[list[str]]]:
    out = []
    for t in re.findall(r"<table[^>]*>(.*?)</table>", md, re.S):
        out.append([[re.sub(r"\*\*|\\", "", c).strip() for c in re.findall(r"<td>(.*?)</td>", tr, re.S)]
                    for tr in re.findall(r"<tr>(.*?)</tr>", t, re.S)])
    return out


ONE_WORD = re.compile(r"^[A-Za-z][A-Za-z'—-]*(?: /[^/]+/| \([^)]*\))?$")


def words_of(s: str) -> list[str]:
    s = re.sub(r"[|‿↘↗*]", " ", s.replace("\\|", " "))
    return [w for w in (re.sub(r"^[^A-Za-z']+|[^A-Za-z']+$", "", t.replace("-", "")).lower() for t in s.split()) if w]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    tts = json.loads((DATA / "tts.json").read_text(encoding="utf-8"))
    tts_keys = [(x["lesson"], x["id"]) for x in tts]
    check(len(tts_keys) == len(set(tts_keys)), "tts.json: duplicate (lesson, id)")
    tts_ids = set(tts_keys)
    for x in tts:
        check(not HANGUL.search(x["text"]), f"tts {x['id']}: Korean text {x['text']!r}")
        check(bool(re.fullmatch(r"[a-z0-9-]+", x["id"])), f"tts id not file-safe: {x['id']!r}")
        check(not re.search(r"[A-Z]{2}|[|‿·●]", x["text"]), f"tts {x['id']}: marks left in {x['text']!r}")
    routes = json.loads((DATA / "routes.json").read_text(encoding="utf-8"))
    index = json.loads((DATA / "reading" / "index.json").read_text(encoding="utf-8"))
    srcs = sorted(SRC.glob("lesson*.md"))
    check(sorted(l["id"] for l in index["lessons"]) == [re.search(r"\d+", p.stem).group(0) for p in srcs],
          "index.json lessons do not match content/reading/lesson*.md")
    for p in srcs:
        md = p.read_text(encoding="utf-8")
        num = re.search(r"\d+", p.stem).group(0)
        key = f"lesson{num}"
        les = json.loads((DATA / "reading" / f"{key}.json").read_text(encoding="utf-8"))
        cards = [c for d in les["decks"] for c in d["cards"]]
        by_type = lambda t: [c for c in cards if c["type"] == t]  # noqa: E731
        for r in (f"#/reading/{num}/lesson", f"#/reading/{num}/practice"):
            check(r in routes, f"routes.json lacks {r}")

        # 1. sentence <details>
        n_details = len(re.findall(r"^<summary>\d+\)", md, re.M))
        sent = [c for c in by_type("sentence") if c["deck"] != "reading"]
        check(n_details == len(sent), f"{key}: {n_details} sentence <details> but {len(sent)} sentence cards")
        # 2. passage
        quote = re.search(r"^> (.*)$", md, re.M)
        n_pass = len(re.findall(r"[.!?](?=\s+[A-Z]|\s*$)", quote.group(1))) if quote else 0
        reading = [c for c in cards if c["deck"] == "reading"]
        check(n_pass == len(reading), f"{key}: passage has {n_pass} sentences but {len(reading)} reading cards")
        mv = re.search(r"<summary>▶ Marked version[^<]*</summary>\s*(.*?)\s*</details>", md, re.S)
        if mv:
            n_mark = len(re.findall(r"[.!?](?=\s|$)", mv.group(1)))
            check(n_mark == len(reading), f"{key}: marked passage has {n_mark} sentences, {len(reading)} cards")
            check(words_of(mv.group(1)) == [w for c in reading for w in words_of(c["marked"])],
                  f"{key}: reading cards' marked text does not cover the marked passage")
        if quote:
            check(words_of(quote.group(1)) == [w for c in reading for w in words_of(c["plain"])],
                  f"{key}: reading cards' plain text does not cover the passage")
        # 3–4. word groups
        wg = tables(section(md, "Word groups"))
        pair_rows = [r for t in wg if len(t) > 1 and all(len(r) >= 2 and ONE_WORD.match(r[0]) and ONE_WORD.match(r[1])
                                                         for r in t[1:]) for r in t[1:]]
        pairs = by_type("pair")
        check(len(pair_rows) == len(pairs), f"{key}: {len(pair_rows)} contrast rows but {len(pairs)} pair cards")
        for r, c in zip(pair_rows, pairs):
            a, b = (words_of(re.sub(r"/[^/]+/|\([^)]*\)", "", x).replace("—", "")) for x in r[:2])
            check([w for part in c["parts"] for w in words_of(part["plain"])] == a + b,
                  f"{key}: pair card {c['id']} != row {r[:2]}")
            check(len(c.get("tts", [])) == 2, f"{key}: pair card {c['id']} needs two tts ids")
        phrase_rows = [r for t in wg if t and len(t[0]) > 1 and t[0][1].lower() == "beat pattern" for r in t[1:]]
        phrases = by_type("phrase")
        check(len(phrase_rows) == len(phrases), f"{key}: {len(phrase_rows)} phrase rows but {len(phrases)} phrase cards")
        for r, c in zip(phrase_rows, phrases):
            check(re.sub(r"\s", "", r[1]) == c["beats"], f"{key}: {c['id']} beats {c['beats']} != column {r[1]}")
            check(words_of(r[0]) == words_of(c["marked"]), f"{key}: {c['id']} marked != row {r[0]!r}")
        # 5. ids
        deck_ids = [d["id"] for d in les["decks"]]
        check(len(deck_ids) == len(set(deck_ids)), f"{key}: duplicate deck ids")
        ids = [c["id"] for c in cards]
        dup = {i for i in ids if ids.count(i) > 1}
        check(not dup, f"{key}: duplicate card ids {sorted(dup)}")
        # 6. per card
        for d in les["decks"]:
            for c in d["cards"]:
                cid = c["id"]
                check(c["deck"] == d["id"], f"{key}: {cid} deck field {c['deck']} in deck {d['id']}")
                check(c["type"] in ("word", "pair", "phrase", "sentence"), f"{key}: {cid} type {c['type']}")
                syl = sum(w["syllables"] for w in c["words"])
                check(len(c["beats"]) == syl, f"{key}: {cid} beats {c['beats']} vs {syl} syllables")
                check(set(c["beats"]) <= {"●", "·"}, f"{key}: {cid} beats {c['beats']!r}")
                flat = "".join("●" if s else "·" for w in c["words"] for s in w["stress"])
                check(flat == c["beats"], f"{key}: {cid} stress {flat} != beats {c['beats']}")
                for w in c["words"]:
                    check(len(w["stress"]) == w["syllables"] >= 1, f"{key}: {cid} word {w['text']} stress/syllables")
                check(c["tune"] in ("↘", "↗"), f"{key}: {cid} tune {c['tune']!r}")
                check(words_of(c["plain"]) == words_of(c["marked"]), f"{key}: {cid} plain/marked words differ")
                check(len(c["words"]) == len(words_of(c["plain"])), f"{key}: {cid} words[] != plain words")
                for t in c["tts"]:
                    check((key, t) in tts_ids, f"{key}: {cid} tts {t} not in tts.json")
        # 7. lesson blocks: tts ids exist, no tts on Korean cells, images exist
        def walk(blocks):
            for b in blocks:
                yield b
                yield from walk(b.get("blocks", []))
        n_cell_tts = 0
        for b in walk(les["blocks"]):
            if b["t"] == "table":
                for row in b["rows"]:
                    for cell in row:
                        for part in [cell] + cell.get("parts", []):
                            if "tts" in part:
                                n_cell_tts += 1
                                check((key, part["tts"]) in tts_ids, f"{key}: cell tts {part['tts']} missing")
                                check(not HANGUL.search(part["html"]), f"{key}: Korean cell has tts: {part['html']}")
            if b["t"] == "img":
                check((ROOT / "site" / b["src"]).exists(), f"{key}: image {b['src']} not in site/")
            if b["t"] == "sentence":
                check(b["card"] in ids, f"{key}: sentence block card {b['card']} missing")
        check(n_cell_tts > 0, f"{key}: no table cell has tts")
        # 8. drill beats column (checks the syllable counter)
        for t in tables(md):
            head = [h.lower() for h in t[0]] if t else []
            if "english" in head and "english beats" in head:
                i, j = head.index("english"), head.index("english beats")
                for r in t[1:]:
                    n = sum(w["syllables"] for w in build.parse_marked(r[i])["words"])
                    check(str(n) == r[j].strip(), f"{key}: drill {r[i]!r} counted {n} syllables, table says {r[j]}")
        # 9. no meta text
        blob = json.dumps(les, ensure_ascii=False)
        for bad in ("Source connection", "No audio recordings", "For teachers", "About the material"):
            check(bad not in blob, f"{key}: meta text {bad!r} in lesson data")
        print(f"{key}: {len(les['decks'])} decks, {len(cards)} cards (sentences {len(sent)}/{n_details}, "
              f"reading {len(reading)}/{n_pass}, pairs {len(pairs)}/{len(pair_rows)}, phrases {len(phrases)}/{len(phrase_rows)}, "
              f"words {len(by_type('word'))}), {n_cell_tts} tts cells")
    for e in errors:
        print("FAIL", e)
    print("test_build:", "FAILED" if errors else "passed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
