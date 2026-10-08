// Offline support. tools/build.py writes site/sw.js from tools/sw.template.js: edit the template, then rebuild.
// App shell, lesson data and audio manifests are precached and served network-first (a cheap revalidation, so a
// deploy shows on the next load; the cache answers offline or when the network is slow). Model-voice clips are
// cached the first time they play and served cache-first, with byte ranges cut from the cached copy (iOS Safari
// asks <audio> for ranges). Nothing the visitor does is stored here.
const VERSION = "bbd3e8d45613";
const AUDIO_VERSION = "97bd6c019a55";
const PRECACHE = [
 "./",
 "index.html",
 "manifest.webmanifest",
 "css/base.css",
 "css/deck.css",
 "css/studio.css",
 "css/tokens.css",
 "js/deck.js",
 "js/lesson.js",
 "js/player.js",
 "js/router.js",
 "img/apple-touch-icon.png",
 "img/icon-192.png",
 "img/icon-512.png",
 "img/icon.svg",
 "img/l02-stops-v3.webp",
 "img/l03-f-vs-p-v2.webp",
 "img/l03-th-vs-s-v2.webp",
 "data/reading/index.json",
 "data/reading/lesson02.json",
 "data/reading/lesson03.json",
 "audio/lesson02/manifest.json",
 "audio/lesson03/manifest.json"
];
const SHELL = `studio-${VERSION}`, AUDIO = `studio-audio-${AUDIO_VERSION}`;
const SLOW_MS = 4000;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL)
    .then((c) => c.addAll(PRECACHE.map((u) => new Request(u, { cache: "reload" }))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  const keep = new Set([SHELL, AUDIO]);
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k.startsWith("studio-") && !keep.has(k)).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function networkFirst(req) {
  const cache = await caches.open(SHELL);
  const net = fetch(req, { cache: "no-cache" }).then((res) => {
    if (res.ok) cache.put(req, res.clone());
    return res;
  });
  const hit = await cache.match(req, { ignoreSearch: true });
  if (!hit) return net;
  const slow = new Promise((ok) => setTimeout(() => ok(hit), SLOW_MS));
  return Promise.race([net.then((res) => (res.ok ? res : hit), () => hit), slow]);
}

function ranged(res, header, buf) {
  const total = buf.byteLength;
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim());
  let start = 0, end = total - 1;
  if (m && m[1] !== "") { start = +m[1]; if (m[2] !== "") end = Math.min(+m[2], total - 1); }
  else if (m && m[2] !== "") start = Math.max(0, total - +m[2]);
  if (!m || start > end || start >= total) {
    return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${total}` } });
  }
  return new Response(buf.slice(start, end + 1), {
    status: 206,
    headers: {
      "Content-Type": res.headers.get("Content-Type") || "audio/mp4",
      "Content-Length": String(end - start + 1),
      "Content-Range": `bytes ${start}-${end}/${total}`,
      "Accept-Ranges": "bytes",
    },
  });
}

async function audio(req) {
  const url = req.url;
  const cache = await caches.open(AUDIO);
  let res = await cache.match(url);
  if (!res) {
    res = await fetch(url); // the whole file, whatever range the element asked for
    if (res.status !== 200) return res;
    await cache.put(url, res.clone());
  }
  const range = req.headers.get("range");
  return range ? ranged(res, range, await res.arrayBuffer()) : res;
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.endsWith(".m4a")) return e.respondWith(audio(req));
  e.respondWith(networkFirst(req));
});
