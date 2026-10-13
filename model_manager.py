"""Model status and downloads for the Models page.

A file counts as installed when ComfyUI lists it (wherever extra_model_paths.yaml
points, e.g. another drive) or when it sits complete in MODELS_DIR/<folder>/.
Downloads run one file at a time in a background thread. Hugging Face's CDN limits
each connection, so a file is fetched as SEGMENTS byte ranges in parallel, each into
`<name>.part<i>` (resumable on its own), then joined and renamed when complete.
Also usable from the command line: `python model_manager.py <model id>`.
"""
import os
import threading
import time
import urllib.request
from pathlib import Path

import comfy_client
from model_catalog import BY_ID, CATALOG, LOADERS

MODELS_DIR = Path(os.environ.get("MODELS_DIR", Path(__file__).parent / "models"))
COMFYUI_DIR = Path(os.environ.get("COMFYUI_DIR", r"C:\cc\ComfyUI"))
CHUNK = 1024 * 1024
SEGMENTS = int(os.environ.get("DOWNLOAD_CONNECTIONS", 8))

# Per model id: {"state": queued|downloading|done|failed|cancelled, "file", "done",
# "total", "speed", "error"}. Only models touched since the server started.
PROGRESS = {}
_queue = []
_lock = threading.Lock()
_wake = threading.Event()
_cancel = set()


def comfy_files(server):
    """Basenames ComfyUI offers per folder (empty sets if it's down)."""
    seen = {}
    for folder, loaders in LOADERS.items():
        names = set()
        for node, field in loaders:
            names.update(n.replace("\\", "/").rsplit("/", 1)[-1]
                         for n in comfy_client.list_models(server, node, field))
        seen[folder] = names
    return seen


def _local(f):
    return MODELS_DIR / f["folder"] / f["name"]


def _model_dirs():
    """Folder -> directories ComfyUI reads it from: its own models/ plus every
    extra_model_paths.yaml entry (a tiny parser: base_path + `folder: subdir` lines)."""
    dirs = {folder: [MODELS_DIR / folder, COMFYUI_DIR / "models" / folder] for folder in LOADERS}
    alias = {"unet": "diffusion_models", "clip": "text_encoders"}
    try:
        lines = (COMFYUI_DIR / "extra_model_paths.yaml").read_text(encoding="utf-8").splitlines()
    except OSError:
        return dirs
    base = None
    for line in lines:
        text = line.split("#", 1)[0].rstrip()
        if not text.strip() or ":" not in text:
            continue
        key, value = (x.strip() for x in text.split(":", 1))
        if not line.startswith((" ", "	")):
            base = None  # a new top-level entry
        elif key == "base_path":
            base = Path(value)
        elif base and alias.get(key, key) in dirs and value:
            dirs[alias.get(key, key)].append(base / value)
    return dirs


def _file_status(f, seen, dirs):
    for d in dirs.get(f["folder"], [MODELS_DIR / f["folder"]]):
        path = d / f["name"]
        if path.exists():
            st = path.stat()
            if st.st_size >= f["size"]:
                return "installed", st.st_size
            # still growing: another download (e.g. a script) is writing it
            return ("writing" if time.time() - st.st_mtime < 120 else "partial"), st.st_size
    have = sum(seg.stat().st_size for seg, _, _ in _segments(f) if seg.exists())
    if have:
        return "partial", have
    if f["name"] in seen.get(f["folder"], ()):  # ComfyUI has it somewhere we can't see
        return "installed", f["size"]
    return "missing", 0


def status(server):
    """The catalog with each model's and file's status, for GET /api/models."""
    seen, dirs = comfy_files(server), _model_dirs()
    out = []
    for m in CATALOG:
        files = []
        for f in m["files"]:
            state, have = _file_status(f, seen, dirs)
            files.append({"name": f["name"], "folder": f["folder"], "size": f["size"],
                          "repo": f["repo"], "state": state, "have": have})
        installed = all(f["state"] == "installed" for f in files)
        out.append({k: v for k, v in m.items() if k != "files"} | {
            "files": files,
            "installed": installed,
            "size": sum(f["size"] for f in m["files"]),
            "missing": sum(f["size"] - f["have"] for f in files if f["state"] != "installed"),
            "progress": PROGRESS.get(m["id"]),
        })
    return {"models": out, "comfy": any(seen.values()), "models_dir": str(MODELS_DIR)}


def installed_ids(server):
    """Ids of the catalog models whose files ComfyUI (or MODELS_DIR) has."""
    seen, dirs = comfy_files(server), _model_dirs()
    if not any(seen.values()):
        return None  # ComfyUI down: unknown
    return {m["id"] for m in CATALOG
            if all(_file_status(f, seen, dirs)[0] == "installed" for f in m["files"])}


def download(model_id, server):
    """Queue the missing files of one model. Returns its progress record."""
    model = BY_ID[model_id]
    seen, dirs = comfy_files(server), _model_dirs()
    todo = [f for f in model["files"] if _file_status(f, seen, dirs)[0] not in ("installed", "writing")]
    with _lock:
        rec = PROGRESS.get(model_id)
        if rec and rec["state"] in ("queued", "downloading"):
            return rec
        _cancel.discard(model_id)
        rec = PROGRESS[model_id] = {
            "state": "queued" if todo else "done", "file": None, "done": 0,
            "total": sum(f["size"] for f in todo), "speed": 0, "error": None}
        if todo:
            _queue.append((model_id, todo))
            _wake.set()
    _ensure_worker()
    return rec


def cancel(model_id):
    with _lock:
        rec = PROGRESS.get(model_id)
        if not rec or rec["state"] not in ("queued", "downloading"):
            return False
        _cancel.add(model_id)
        if rec["state"] == "queued":
            _queue[:] = [q for q in _queue if q[0] != model_id]
            rec["state"] = "cancelled"
    return True


_worker = None


def _ensure_worker():
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_work, name="model-downloads", daemon=True)
        _worker.start()


def _work():
    while True:
        _wake.wait()
        with _lock:
            if not _queue:
                _wake.clear()
                continue
            model_id, files = _queue.pop(0)
        rec = PROGRESS[model_id]
        rec["state"] = "downloading"
        try:
            for f in files:
                _fetch(model_id, f, rec)
            rec["state"] = "done"
        except _Cancelled:
            rec["state"] = "cancelled"
        except Exception as exc:  # network, disk full, 404 ...
            rec.update(state="failed", error=str(exc))


class _Cancelled(Exception):
    pass


def _segments(f):
    """(file, first byte, last byte) for each parallel part of a download."""
    path, size = _local(f), f["size"]
    n = max(1, min(SEGMENTS, size // (64 * CHUNK)))  # small files: fewer parts
    step = -(-size // n)
    return [(path.with_name(f"{path.name}.part{i}"), i * step, min((i + 1) * step, size) - 1)
            for i in range(n)]


def _fetch_segment(model_id, url, seg, first, last, errors):
    """Download bytes first..last into `seg`, resuming from its size; retries on
    network errors."""
    for attempt in range(30):
        have = seg.stat().st_size if seg.exists() else 0
        if first + have > last:
            return
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={first + have}-{last}"})
            with urllib.request.urlopen(req, timeout=60) as r, seg.open("ab") as out:
                if r.status != 206:
                    raise RuntimeError("the server doesn't support resuming (no HTTP 206)")
                while True:
                    if model_id in _cancel:
                        return
                    chunk = r.read(CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
        except RuntimeError as exc:
            errors.append(str(exc))
            return
        except Exception:
            time.sleep(min(60, 2 ** attempt))  # dropped connection: back off and resume
    if seg.stat().st_size < last - first + 1:
        errors.append(f"{seg.name}: gave up after 30 tries")


def _fetch(model_id, f, rec):
    path = _local(f)
    path.parent.mkdir(parents=True, exist_ok=True)
    segments = _segments(f)
    legacy = path.with_name(path.name + ".part")  # an older single-stream download
    if path.exists() and path.stat().st_size < f["size"]:
        # an interrupted download under the final name (e.g. from curl): resume it,
        # unless something is still writing to it
        if time.time() - path.stat().st_mtime < 120:
            raise RuntimeError(f"{f['name']} is still being written by another download")
        path.replace(legacy)
    first_seg = segments[0][0]
    if legacy.exists() and not first_seg.exists() and legacy.stat().st_size <= segments[0][2] + 1:
        legacy.replace(first_seg)  # it starts at byte 0, so it is part 0's beginning
    base = rec["done"]
    rec["file"] = f["name"]
    errors = []
    threads = [threading.Thread(target=_fetch_segment, daemon=True,
                                args=(model_id, f["url"], seg, a, b, errors))
               for seg, a, b in segments]
    for t in threads:
        t.start()
    have = lambda: sum(seg.stat().st_size for seg, _, _ in segments if seg.exists())
    t0, mark = time.time(), have()
    while any(t.is_alive() for t in threads):
        time.sleep(1)
        now = have()
        rec["done"] = base + now
        if time.time() - t0 >= 3:
            rec["speed"] = (now - mark) / (time.time() - t0)
            t0, mark = time.time(), now
    if model_id in _cancel:
        raise _Cancelled()
    if errors or have() < f["size"]:
        raise RuntimeError(errors[0] if errors else f"{f['name']}: download ended early")
    joined = path.with_name(path.name + ".joining")
    with joined.open("wb") as out:
        for seg, _, _ in segments:
            with seg.open("rb") as src:
                while chunk := src.read(16 * CHUNK):
                    out.write(chunk)
    if joined.stat().st_size != f["size"]:
        raise RuntimeError(f"{f['name']}: joined file has the wrong size")
    joined.replace(path)
    for seg, _, _ in segments:
        seg.unlink()
    rec["done"] = base + f["size"]


if __name__ == "__main__":
    import sys
    server = os.environ.get("COMFY_SERVER", "http://127.0.0.1:8188")
    for model_id in sys.argv[1:]:
        rec = download(model_id, server)
        while rec["state"] in ("queued", "downloading"):
            time.sleep(10)
            print(f"{time.strftime('%H:%M')} {model_id}: {rec['state']} {rec['file']} "
                  f"{rec['done'] / 1e9:.2f}/{rec['total'] / 1e9:.2f} GB "
                  f"at {rec['speed'] / 1e6:.2f} MB/s", flush=True)
        print(f"{model_id}: {rec['state']} {rec['error'] or ''}", flush=True)
