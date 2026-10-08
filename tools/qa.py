"""Browser QA for the site. Serves site/ on a free port in a thread, drives Playwright, and closes both before exiting.

Usage:
  python tools/qa.py --smoke                        every hash of site/data/routes.json (else '#/') opens on desktop
                                                    chromium 1280x800, iPhone 13 webkit and Galaxy S24 chromium
                                                    without console/page errors or horizontal scroll
  python tools/qa.py --shot <hash> [--device desktop|iphone|galaxy] [--dark] [--out name]   -> logs/shots/<name>.png
  python tools/qa.py --eval <hash> <js>             run JS in the page, print the result as JSON
  python tools/qa.py --audit                        every route (and the first deck of each practice tab) on iPhone
                                                    and Galaxy: no horizontal scroll, every control's hit area >= 44px,
                                                    canPlayType('audio/mp4'), a model clip plays to its end (webkit;
                                                    Playwright chromium has no AAC), first-screen bytes without audio
                                                    <= 300 KB as sent (the local server gzips text like Pages)
  python tools/qa.py --pwa                          service worker on Galaxy and iPhone: precache complete, every route
                                                    and a played clip (byte ranges, <audio>) work offline, icons resolve
  python tools/qa.py ... --base <url>               test a deployed site instead of the local site/
"""
import argparse
import functools
import gzip
import http.server
import json
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
SHOTS = ROOT / "logs" / "shots"
SETTLE_MS = 1000
DEVICES = {  # name -> (engine, playwright device name or None, viewport for desktop)
    "desktop": ("chromium", None),
    "iphone": ("webkit", "iPhone 13"),
    "galaxy": ("chromium", "Galaxy S24"),
}


class Quiet(http.server.SimpleHTTPRequestHandler):
    """Serves site/ and, like GitHub Pages, gzips text files for clients that accept it."""
    GZIP = {".html", ".css", ".js", ".json", ".webmanifest", ".svg"}
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".webmanifest": "application/manifest+json",
                      ".m4a": "audio/mp4", ".webp": "image/webp"}

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = Path(self.translate_path(self.path))
        if path.is_dir():
            path = path / "index.html"
        if path.suffix not in self.GZIP or not path.is_file() or "gzip" not in self.headers.get("Accept-Encoding", ""):
            return super().do_GET()
        body = gzip.compress(path.read_bytes(), 6)
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 128


def serve():
    httpd = Server(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def norm(h: str) -> str:
    h = h.lstrip("#")
    return "#" + (h if h.startswith("/") else "/" + h)


def routes() -> list[str]:
    f = SITE / "data" / "routes.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else ["#/"]


def open_page(pw, base, h, device, dark=False, errors=None, on_response=None):
    engine, dev = DEVICES[device]
    browser = getattr(pw, engine).launch()
    opts = dict(pw.devices[dev]) if dev else {"viewport": {"width": 1280, "height": 800}}
    opts["color_scheme"] = "dark" if dark else "light"
    ctx = browser.new_context(service_workers="block", **opts)
    page = ctx.new_page()
    if errors is not None:
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("requestfailed", lambda r: errors.append(f"requestfailed: {r.url} {r.failure}"))
        page.on("response", lambda r: errors.append(f"http {r.status}: {r.url}") if r.status >= 400 else None)
    if on_response:
        page.on("response", on_response)
    page.goto(f"{base}/{norm(h)}", wait_until="load")
    page.wait_for_timeout(SETTLE_MS)
    return browser, page


def smoke(pw, base) -> int:
    bad = 0
    for h in routes():
        for device in DEVICES:
            errors: list[str] = []
            browser, page = open_page(pw, base, h, device, errors=errors)
            try:
                w = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                if w[0] > w[1]:
                    errors.append(f"horizontal scroll: scrollWidth {w[0]} > clientWidth {w[1]}")
            finally:
                browser.close()
            print(f"{'FAIL' if errors else 'ok  '} {device:8} {h}")
            for e in errors:
                print("     ", e)
            bad += bool(errors)
    print("smoke:", "FAILED" if bad else "passed")
    return 1 if bad else 0


FIRST_SCREEN_BUDGET = 300 * 1024
MIN_TARGET = 44
# Visible controls whose hit area (box, or a pseudo-element that extends it) is under 44px in either direction.
TARGETS_JS = r"""(min) => {
  const sel = 'a[href], button, summary, input, select, textarea, [role=button], [tabindex]:not([tabindex="-1"])';
  const out = [];
  for (let el of document.querySelectorAll(sel)) {
    if (el.closest('[hidden], [inert]') || (el.disabled && !el.dataset.tts)) continue;
    if (el.labels && el.labels.length) el = el.labels[0]; // a visually hidden checkbox is tapped through its label
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === 'hidden') continue;
    if (r.width >= min - 0.5 && r.height >= min - 0.5) continue;
    // a hit area grown by ::before/::after counts: probe 21px either side of the centre
    el.scrollIntoView({ block: 'center', inline: 'center' });
    const q = el.getBoundingClientRect(), cx = q.left + q.width / 2, cy = q.top + q.height / 2, h = min / 2 - 1;
    const hits = [[cx - h, cy], [cx + h, cy], [cx, cy - h], [cx, cy + h]].every(([x, y]) => {
      const t = document.elementFromPoint(x, y);
      return t && (t === el || el.contains(t));
    });
    if (hits) continue;
    const label = (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 30);
    out.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} "${label}" ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  window.scrollTo(0, 0);
  return out;
}"""
# Play the first enabled model clip on the page through a fresh <audio> and wait for it to end.
PLAY_JS = r"""async () => {
  const a = new Audio();
  const can = a.canPlayType('audio/mp4');
  const btn = document.querySelector('[data-tts]:not([disabled])');
  if (!btn) return { can, played: false, why: 'no enabled clip' };
  const lesson = btn.closest('[data-lesson]').dataset.lesson, id = btn.dataset.tts.split(' ')[0];
  a.src = `audio/${lesson}/${id}.f.100.m4a`;
  const res = await new Promise((ok) => {
    const t = setTimeout(() => ok({ played: false, why: `timeout at ${a.currentTime}s, readyState ${a.readyState}` }), 8000);
    a.addEventListener('ended', () => { clearTimeout(t); ok({ played: true, dur: a.duration }); });
    a.addEventListener('error', () => { clearTimeout(t); ok({ played: false, why: `error ${a.error && a.error.code}` }); });
    a.play().catch((e) => { clearTimeout(t); ok({ played: false, why: String(e) }); });
  });
  return { can, src: a.src.split('/audio/')[1], ...res };
}"""


def audit_page(page, label: str, errs: list[str]) -> None:
    w = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    if w[0] > w[1]:
        errs.append(f"{label}: horizontal scroll {w[0]} > {w[1]}")
    for t in page.evaluate(TARGETS_JS, MIN_TARGET):
        errs.append(f"{label}: target < {MIN_TARGET}px: {t}")


def audit(pw, base) -> int:
    errs: list[str] = []
    for device in ("iphone", "galaxy"):
        engine = DEVICES[device][0]
        for h in routes():
            wire: dict[str, int] = {}
            raw: dict[str, int] = {}

            def seen(r):
                if r.ok and ".m4a" not in r.url:
                    try:
                        raw[r.url] = len(r.body())
                        wire[r.url] = r.request.sizes()["responseBodySize"]
                    except Exception:
                        pass

            browser, page = open_page(pw, base, h, device, on_response=seen)
            try:
                total = sum(wire.values())
                print(f"{device:7} {h:24} first screen {total / 1024:6.1f} KB sent ({sum(raw.values()) / 1024:.1f} KB "
                      f"unpacked) in {len(wire)} files, audio excluded")
                if total > FIRST_SCREEN_BUDGET:
                    errs.append(f"{device} {h}: first screen {total / 1024:.1f} KB > {FIRST_SCREEN_BUDGET // 1024} KB")
                audit_page(page, f"{device} {h}", errs)
                if h.endswith("/practice"):
                    page.click(".dl-row")
                    page.wait_for_timeout(600)
                    audit_page(page, f"{device} {h} deck", errs)
                    page.click(".fc-reveal")
                    page.wait_for_timeout(400)
                    audit_page(page, f"{device} {h} deck+back", errs)
                if h.endswith("/lesson"):
                    r = page.evaluate(PLAY_JS)
                    print(f"        audio: canPlayType('audio/mp4')={r['can']!r} {r.get('src', '')} "
                          f"{'played ' + format(r['dur'], '.2f') + 's' if r['played'] else 'not played: ' + r['why']}")
                    if engine == "webkit" and not r["can"]:
                        errs.append(f"{device}: canPlayType('audio/mp4') is empty")
                    if engine == "webkit" and not r["played"]:
                        errs.append(f"{device} {h}: clip did not play: {r['why']}")
            finally:
                browser.close()
    for e in errs:
        print("FAIL", e)
    print("audit:", "FAILED" if errs else "passed")
    return 1 if errs else 0


PWA_JS = r"""async () => {
  const reg = await navigator.serviceWorker.ready;
  const names = await caches.keys();
  const shell = names.find((n) => /^studio-[0-9a-f]+$/.test(n));
  const keys = shell ? (await (await caches.open(shell)).keys()).map((r) => r.url) : [];
  return { active: !!reg.active, controlled: !!navigator.serviceWorker.controller, names, cached: keys.length };
}"""
RANGES_JS = r"""async (u) => {
  const a = await fetch(u), b = await fetch(u, { headers: { Range: 'bytes=0-1' } });
  const c = await fetch(u, { headers: { Range: 'bytes=100-' } });
  return [a.status, (await a.arrayBuffer()).byteLength, b.status, b.headers.get('content-range'),
          (await b.arrayBuffer()).byteLength, c.status, (await c.arrayBuffer()).byteLength];
}"""


def pwa(pw, remote=None) -> int:
    """Offline = the local server is shut down (Playwright WebKit's set_offline also blocks service-worker
    responses); with --base the deployed site is cut off by set_offline on chromium only."""
    errs: list[str] = []
    sw = (SITE / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"const PRECACHE = (\[.*?\]);", sw, re.S)
    precache = json.loads(m.group(1)) if m else []
    man = json.loads((SITE / "manifest.webmanifest").read_text(encoding="utf-8"))
    for icon in man["icons"]:
        if not (SITE / icon["src"]).exists():
            errs.append(f"manifest icon missing: {icon['src']}")
    for device in ("galaxy",) if remote else ("galaxy", "iphone"):
        engine, dev = DEVICES[device]
        httpd, base = (None, remote) if remote else serve()
        browser = getattr(pw, engine).launch()
        try:
            ctx = browser.new_context(**pw.devices[dev])
            page = ctx.new_page()
            page.on("pageerror", lambda e: errs.append(f"{device} pageerror: {e}"))
            page.goto(f"{base}/#/", wait_until="load")
            page.evaluate(PWA_JS)
            page.reload(wait_until="load")  # the first visit may finish before clients.claim() takes it over
            st = page.evaluate(PWA_JS)
            print(f"{device} service worker:", st)
            if not st["active"] or not st["controlled"] or st["cached"] != len(precache):
                errs.append(f"{device} precache: {st['cached']} cached, {len(precache)} listed")
            page.goto(f"{base}/#/reading/02/lesson", wait_until="load")
            page.wait_for_timeout(SETTLE_MS)
            btn = page.locator("[data-tts]:not([disabled])").first
            lesson = btn.evaluate("b => b.closest('[data-lesson]').dataset.lesson")
            clip = f"audio/{lesson}/{btn.get_attribute('data-tts').split(' ')[0]}.f.100.m4a"
            n = page.evaluate("async (u) => (await (await fetch(u)).arrayBuffer()).byteLength", clip)
            if httpd:
                httpd.shutdown()
                httpd.server_close()
            else:
                ctx.set_offline(True)
            for h in routes():
                page.goto(f"{base}/{norm(h)}", wait_until="load")
                page.wait_for_timeout(SETTLE_MS)
                ok = page.evaluate("!!document.querySelector('#view').children.length && !document.querySelector('#view .empty')")
                print(f"{'ok  ' if ok else 'FAIL'} {device} offline {h}")
                if not ok:
                    errs.append(f"{device} offline route failed: {h}")
            r = page.evaluate(RANGES_JS, clip)
            print(f"{device} offline clip {clip}: {r} (online {n} bytes)")
            if r != [200, n, 206, f"bytes 0-1/{n}", 2, 206, n - 100]:
                errs.append(f"{device} offline clip ranges wrong: {r}")
            page.goto(f"{base}/#/reading/02/lesson", wait_until="load")
            page.wait_for_timeout(SETTLE_MS)
            r = page.evaluate(PLAY_JS)
            if engine == "webkit":
                # Playwright's Windows WebKit loads media through Media Foundation, outside the service worker, so
                # this cannot pass here; the worker's byte ranges were checked with fetch() above.
                print(f"{device} offline <audio> (informational, media bypasses the worker here): {r}")
            else:
                print(f"{device} offline <audio>: {r}")
                if not r["played"]:
                    errs.append(f"{device} cached clip did not play offline: {r.get('why')}")
            ctx.close()
        finally:
            browser.close()
            if httpd:
                httpd.shutdown()
                httpd.server_close()
    for e in errs:
        print("FAIL", e)
    print("pwa:", "FAILED" if errs else "passed")
    return 1 if errs else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--smoke", action="store_true")
    g.add_argument("--shot", metavar="HASH")
    g.add_argument("--eval", nargs=2, metavar=("HASH", "JS"))
    g.add_argument("--audit", action="store_true")
    g.add_argument("--pwa", action="store_true")
    ap.add_argument("--device", choices=list(DEVICES), default="desktop")
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--base", help="deployed site URL; default serves site/ locally")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright
    httpd = None
    if a.base:
        base = a.base.rstrip("/")
    else:
        httpd, base = serve()
    try:
        with sync_playwright() as pw:
            if a.smoke:
                return smoke(pw, base)
            if a.audit:
                return audit(pw, base)
            if a.pwa:
                return pwa(pw, a.base and base)
            h = a.shot or a.eval[0]
            browser, page = open_page(pw, base, h, a.device, a.dark)
            try:
                if a.shot:
                    SHOTS.mkdir(parents=True, exist_ok=True)
                    name = a.out or (norm(h).strip("#/").replace("/", "-") or "home") + f"-{a.device}" + ("-dark" if a.dark else "")
                    path = SHOTS / f"{name}.png"
                    page.screenshot(path=str(path))
                    print(path)
                else:
                    print(json.dumps(page.evaluate(a.eval[1]), ensure_ascii=False))
            finally:
                browser.close()
        return 0
    finally:
        if httpd:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    sys.exit(main())
