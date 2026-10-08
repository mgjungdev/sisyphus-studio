"""Kokoro TTS for every entry of site/data/tts.json.

  python tools/tts.py                  synthesize what is missing or changed (all lessons)
  python tools/tts.py --only lesson02  only one lesson
  python tools/tts.py --check          verify files, durations, RMS and manifests (no synthesis)

Output: site/audio/<lesson>/<id>.<f|m>.<100|80>.m4a   (AAC 48 kbps mono)
        site/audio/<lesson>/manifest.json   {id: {hash, dur}}
hash = sha1(text, voice, speed, model version); only entries whose hash changed are rebuilt.
Leading/trailing silence is trimmed to 50 ms. Models are downloaded to tools/models/ (git-ignored).
"""
import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "tools" / "models"
AUDIO = ROOT / "site" / "audio"
TTS_JSON = ROOT / "site" / "data" / "tts.json"
MODEL_VERSION = "kokoro-v1.0"
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]
VOICES = {"f": "af_heart", "m": "am_michael"}
SPEEDS = {"100": 1.0, "80": 0.8}
SR = 24000
PAD = 0.05          # seconds of silence kept at each end
SIL_DB = -50        # below peak * this = silence when trimming
MIN_DUR, MAX_DUR, MIN_RMS = 0.3, 15.0, 0.005


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def variants():
    for v in VOICES:
        for s in SPEEDS:
            yield v, s


def fname(tid: str, v: str, s: str) -> str:
    return f"{tid}.{v}.{s}.m4a"


def item_hash(text: str, v: str, s: str) -> str:
    key = json.dumps([text, VOICES[v], SPEEDS[s], MODEL_VERSION], ensure_ascii=False)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def load_items(only: str | None) -> dict[str, list[dict]]:
    items = json.loads(TTS_JSON.read_text(encoding="utf-8"))
    by: dict[str, list[dict]] = {}
    for it in items:
        if only and it["lesson"] != only:
            continue
        by.setdefault(it["lesson"], []).append(it)
    return by


def read_manifest(lesson: str) -> dict:
    p = AUDIO / lesson / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_manifest(lesson: str, m: dict) -> None:
    p = AUDIO / lesson / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def ensure_models() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        p = MODELS / f
        if not p.exists() or p.stat().st_size == 0:
            print(f"downloading {f} ...", flush=True)
            tmp = p.with_suffix(p.suffix + ".part")
            urllib.request.urlretrieve(RELEASE + f, tmp)
            tmp.replace(p)


def trim(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    peak = float(np.abs(x).max()) if x.size else 0.0
    if peak == 0:
        return x
    idx = np.nonzero(np.abs(x) > peak * 10 ** (SIL_DB / 20))[0]
    pad = int(PAD * SR)
    a, b = max(idx[0] - pad, 0), min(idx[-1] + 1 + pad, x.size)
    out = x[a:b]
    # exact 50 ms of lead/tail even when the source had less
    lead, tail = idx[0] - a, b - (idx[-1] + 1)
    return np.concatenate([np.zeros(pad - lead, np.float32), out, np.zeros(pad - tail, np.float32)])


def encode(x: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.m4a")
    cmd = [ffmpeg(), "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
           "-c:a", "aac", "-b:a", "48k", "-ac", "1", "-movflags", "+faststart", str(tmp)]
    r = subprocess.run(cmd, input=x.astype("<f4").tobytes(), capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace"))
    tmp.replace(path)


def decode(path: Path) -> np.ndarray:
    r = subprocess.run([ffmpeg(), "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ar", str(SR), "-ac", "1", "-"],
                       capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace"))
    return np.frombuffer(r.stdout, dtype="<f4")


_kokoro = None


def _work(job):
    """Runs in a worker process: synthesize one file."""
    global _kokoro
    if _kokoro is None:
        import onnxruntime as ort
        from kokoro_onnx import Kokoro
        so = ort.SessionOptions()
        so.intra_op_num_threads = 2
        _kokoro = Kokoro.from_session(ort.InferenceSession(str(MODELS / FILES[0]), so, providers=["CPUExecutionProvider"]),
                                      str(MODELS / FILES[1]))
    lesson, tid, text, v, s, h = job
    samples, sr = _kokoro.create(text, voice=VOICES[v], speed=SPEEDS[s], lang="en-us")
    assert sr == SR, sr
    x = trim(samples)
    encode(x, AUDIO / lesson / fname(tid, v, s))
    return lesson, f"{tid}|{v}|{s}", h, round(x.size / SR, 3)


def generate(only: str | None, jobs: int) -> int:
    from concurrent.futures import ProcessPoolExecutor
    ensure_models()
    by = load_items(only)
    if only and not by:
        sys.exit(f"no tts entries for lesson '{only}'")
    mans, todo = {}, []
    for lesson, items in by.items():
        man = read_manifest(lesson)
        ids = {it["id"] for it in items}
        for k in [k for k in man if k.split("|")[0] not in ids]:
            del man[k]
        mans[lesson] = man
        for it in items:
            for v, s in variants():
                h = item_hash(it["text"], v, s)
                path = AUDIO / lesson / fname(it["id"], v, s)
                if man.get(f"{it['id']}|{v}|{s}", {}).get("hash") != h or not path.exists():
                    todo.append((lesson, it["id"], it["text"], v, s, h))
    print(f"{len(todo)} files to synthesize", flush=True)
    if todo:
        with ProcessPoolExecutor(jobs) as ex:
            for n, (lesson, key, h, dur) in enumerate(ex.map(_work, todo, chunksize=4), 1):
                mans[lesson][key] = {"hash": h, "dur": dur}
                if n % 50 == 0:
                    for l, m in mans.items():
                        write_manifest(l, m)
                    print(f"{n}/{len(todo)}", flush=True)
    for l, m in mans.items():
        write_manifest(l, m)
    print(f"synthesized {len(todo)} files")
    return 0


def check(only: str | None) -> int:
    by = load_items(only)
    errs: list[str] = []
    stats = {}
    for lesson, items in by.items():
        man = read_manifest(lesson)
        want = set()
        for it in items:
            for v, s in variants():
                key = f"{it['id']}|{v}|{s}"
                want.add(key)
                path = AUDIO / lesson / fname(it["id"], v, s)
                if not path.exists() or path.stat().st_size == 0:
                    errs.append(f"{lesson}/{path.name}: 파일 없음")
                    continue
                m = man.get(key)
                if not m:
                    errs.append(f"{lesson}/{path.name}: manifest에 없음")
                    continue
                if m["hash"] != item_hash(it["text"], v, s):
                    errs.append(f"{lesson}/{path.name}: manifest hash가 텍스트/설정과 다름(다시 생성 필요)")
                x = decode(path)
                dur = x.size / SR
                rms = float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
                if not MIN_DUR <= dur <= MAX_DUR:
                    errs.append(f"{lesson}/{path.name}: 길이 {dur:.2f}s (허용 {MIN_DUR}–{MAX_DUR})")
                if rms < MIN_RMS:
                    errs.append(f"{lesson}/{path.name}: 무음에 가까움 (RMS {rms:.4f})")
                if abs(dur - m["dur"]) > 0.15:
                    errs.append(f"{lesson}/{path.name}: manifest dur {m['dur']} ≠ 실제 {dur:.2f}")
                stats[(lesson, key)] = (dur, float(np.abs(x).max()))
        for k in man:
            if k not in want:
                errs.append(f"{lesson}: manifest에 남는 항목 {k}")
    if errs:
        print(f"{len(errs)} problems:")
        print("\n".join(errs[:40]))
        return 1
    n = len(stats)
    durs = [d for d, _ in stats.values()]
    print(f"ok: {n} files, dur {min(durs):.2f}-{max(durs):.2f}s")
    return 0


def report(words: list[str]) -> None:
    for lesson, items in load_items(None).items():
        for it in items:
            if it["id"] in words:
                for v, s in variants():
                    x = decode(AUDIO / lesson / fname(it["id"], v, s))
                    print(f"{it['id']} {v}.{s}: {x.size / SR:.2f}s peak {np.abs(x).max():.2f}")


sys.stdout.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", metavar="LESSON")
    ap.add_argument("--jobs", type=int, default=8, help="worker processes")
    ap.add_argument("--report", nargs="*", metavar="ID", help="print duration/peak of given ids")
    a = ap.parse_args()
    if a.report is not None:
        report(a.report)
        sys.exit(0)
    sys.exit(check(a.only) if a.check else generate(a.only, a.jobs))
