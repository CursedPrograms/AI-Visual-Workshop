"""Minimal ComfyUI client for the Qwen-Image 2.1 GGUF workflows.

Queues the API-format graph (text-to-image, image edit or masked inpaint of an
uploaded photo) on a running ComfyUI server, waits for the job to finish and pulls the
rendered images back out. Standard library only.
"""
import json
import random
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:  # optional: live step progress over ComfyUI's websocket
    import websocket
except ImportError:
    websocket = None

WORKFLOWS = Path(__file__).parent / "workflows"
WORKFLOW = WORKFLOWS / "qwen_image_2.1_gguf_t2i_api.json"
EDIT_WORKFLOW = WORKFLOWS / "qwen_image_2.1_gguf_edit_api.json"
INPAINT_WORKFLOW = WORKFLOWS / "qwen_image_2.1_gguf_inpaint_api.json"
KREA2_WORKFLOW = WORKFLOWS / "krea2_turbo_gguf_t2i_api.json"
# Text-to-image model families: "qwen" (Qwen-Image 2.1) or "krea2" (Krea 2 Turbo).
T2I_WORKFLOWS = {"qwen": WORKFLOW, "krea2": KREA2_WORKFLOW}
MAX_SEED = 2 ** 53


class ComfyError(RuntimeError):
    """Raised when ComfyUI is unreachable, rejects the graph or times out."""


class Cancelled(ComfyError):
    """Raised when a job is cancelled with cancel()."""


_cancelled = set()  # prompt_ids cancelled while a caller is still waiting on them


def load_workflow(path=WORKFLOW):
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_lora(wf, lora, strength):
    """Insert a LoraLoaderModelOnly between the model loader and the sampler."""
    if not lora:
        return
    wf["20"] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {"model": ["1", 0], "lora_name": lora,
                   "strength_model": float(strength)},
    }
    wf["6"]["inputs"]["model"] = ["20", 0]


def build_workflow(prompt, *, model="qwen", negative="", width=1024, height=1024,
                   steps=25, cfg=1.0, seed=None, batch=1, unet=None, clip=None,
                   lora=None, lora_strength=1.0,
                   sampler="euler", scheduler="simple", prefix=None):
    """Patch the text-to-image graph for `model` ("qwen" or "krea2").

    Krea 2 Turbo is distilled: use about 8 steps and cfg 1 (it has no negative
    prompt). Returns (workflow_dict, resolved_seed).
    """
    if model not in T2I_WORKFLOWS:
        raise ValueError(f"unknown model {model!r}; expected one of {sorted(T2I_WORKFLOWS)}")
    wf = load_workflow(T2I_WORKFLOWS[model])
    if unet:
        wf["1"]["inputs"]["unet_name"] = unet
    if clip:
        wf["2"]["inputs"]["clip_name"] = clip
    if model == "krea2":
        wf["4"]["inputs"]["text"] = prompt
    else:
        wf["4"]["inputs"]["prompt"] = prompt
        wf["4"]["inputs"]["negative_prompt"] = negative
    _apply_lora(wf, lora, lora_strength)
    wf["5"]["inputs"].update(width=int(width), height=int(height),
                             batch_size=int(batch))
    seed = int(seed) if seed not in (None, "") else random.randint(0, MAX_SEED)
    wf["6"]["inputs"].update(seed=seed, steps=int(steps), cfg=float(cfg),
                             sampler_name=sampler, scheduler=scheduler)
    if prefix:
        wf["8"]["inputs"]["filename_prefix"] = prefix
    return wf, seed


def build_edit_workflow(prompt, image, *, negative="", resolution=1024, steps=25,
                        cfg=1.0, seed=None, unet=None, clip=None,
                        lora=None, lora_strength=1.0,
                        sampler="euler", scheduler="simple",
                        prefix="Qwen_image_2.1_gguf_edit"):
    """Patch the edit graph. `image` is a filename already uploaded to ComfyUI.

    The output keeps the input photo's aspect ratio, scaled to about
    resolution x resolution pixels. Returns (workflow_dict, resolved_seed).
    """
    wf = load_workflow(EDIT_WORKFLOW)
    if unet:
        wf["1"]["inputs"]["unet_name"] = unet
    if clip:
        wf["2"]["inputs"]["clip_name"] = clip
    wf["4"]["inputs"].update(prompt=prompt, negative_prompt=negative,
                             resolution=int(resolution))
    _apply_lora(wf, lora, lora_strength)
    seed = int(seed) if seed not in (None, "") else random.randint(0, MAX_SEED)
    wf["6"]["inputs"].update(seed=seed, steps=int(steps), cfg=float(cfg),
                             sampler_name=sampler, scheduler=scheduler)
    wf["8"]["inputs"]["filename_prefix"] = prefix
    wf["9"]["inputs"]["image"] = image
    return wf, seed


def build_inpaint_workflow(prompt, image, mask, *, reference=None, negative="", steps=25,
                           cfg=1.0, denoise=1.0, seed=None, unet=None, clip=None,
                           lora=None, lora_strength=1.0,
                           sampler="euler", scheduler="simple",
                           prefix="Qwen_image_2.1_gguf_inpaint"):
    """Patch the inpaint graph. `image` and `mask` are filenames already uploaded
    to ComfyUI, at the same size (multiples of 32); white in the mask is
    regenerated, black is kept. Returns (workflow_dict, resolved_seed).

    `reference` (optional, an uploaded filename) replaces `image` as the picture
    the model sees. Uncrop needs this: shown the grey-padded canvas, the model
    copies the grey border instead of filling it, so it gets the unpadded photo.
    """
    wf = load_workflow(INPAINT_WORKFLOW)
    if unet:
        wf["1"]["inputs"]["unet_name"] = unet
    if clip:
        wf["2"]["inputs"]["clip_name"] = clip
    wf["4"]["inputs"].update(prompt=prompt, negative_prompt=negative)
    _apply_lora(wf, lora, lora_strength)
    seed = int(seed) if seed not in (None, "") else random.randint(0, MAX_SEED)
    wf["6"]["inputs"].update(seed=seed, steps=int(steps), cfg=float(cfg),
                             denoise=float(denoise),
                             sampler_name=sampler, scheduler=scheduler)
    wf["8"]["inputs"]["filename_prefix"] = prefix
    wf["9"]["inputs"]["image"] = image
    wf["10"]["inputs"]["image"] = mask
    if reference:
        wf["14"] = {"class_type": "LoadImage", "inputs": {"image": reference}}
        wf["4"]["inputs"]["images.image_1"] = ["14", 0]
        wf["4"]["inputs"]["resolution"] = 1024
    return wf, seed


def _get(server, path, timeout=10):
    with urllib.request.urlopen(f"{server}{path}", timeout=timeout) as r:
        return json.load(r)


def list_models(server, node, field):
    """Return the filenames ComfyUI offers for one loader input, e.g.
    ("LoraLoaderModelOnly", "lora_name") -> every LoRA it can see."""
    try:
        info = _get(server, f"/object_info/{node}")
        return list(info[node]["input"]["required"][field][0])
    except Exception:
        return []


def ping(server, timeout=3):
    """Return True if a ComfyUI server answers at `server`."""
    try:
        _get(server, "/system_stats", timeout=timeout)
        return True
    except Exception:
        return False


def queue(server, wf, client_id, front=False):
    """Queue a graph; front=True puts it ahead of everything already pending."""
    body = {"prompt": wf, "client_id": client_id}
    if front:
        body["front"] = True
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{server}/prompt", data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)["prompt_id"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise ComfyError(f"ComfyUI rejected the workflow ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise ComfyError(f"Cannot reach ComfyUI at {server}: {e.reason}") from e


def _unique(filename):
    """photo.png -> photo_1a2b3c4d.png, so queued jobs (and the user's own files in
    ComfyUI's input folder) never overwrite each other."""
    p = Path(filename)
    return f"{p.stem}_{uuid.uuid4().hex[:8]}{p.suffix or '.png'}"


def upload_image(server, filename, data):
    """Upload image bytes to ComfyUI's input folder; returns the stored name."""
    boundary = uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        data,
        f"\r\n--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue',
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{server}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise ComfyError(f"ComfyUI rejected the upload ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise ComfyError(f"Cannot reach ComfyUI at {server}: {e.reason}") from e
    return f"{res['subfolder']}/{res['name']}" if res.get("subfolder") else res["name"]


def cancel(server, prompt_id):
    """Cancel one job: drop it from the queue if pending, interrupt it if running.

    Other users' jobs are left alone.
    """
    _cancelled.add(prompt_id)
    for path, body in (("/queue", {"delete": [prompt_id]}),
                       ("/interrupt", {"prompt_id": prompt_id})):
        req = urllib.request.Request(
            f"{server}{path}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=10).close()
        except urllib.error.URLError as e:
            raise ComfyError(f"Cannot reach ComfyUI at {server}: {e.reason}") from e


def jobs_ahead(server, prompt_id):
    """How many ComfyUI jobs run before prompt_id (running + earlier pending),
    or None if it isn't in the queue."""
    q = _get(server, "/queue")
    pending = sorted(q.get("queue_pending", []), key=lambda item: item[0])
    for i, item in enumerate(pending):
        if item[1] == prompt_id:
            return len(q.get("queue_running", [])) + i
    return None


def _check_cancelled(prompt_id):
    if prompt_id in _cancelled:
        _cancelled.discard(prompt_id)
        raise Cancelled("Cancelled.")


def _queue_state(server, prompt_id):
    """"running", "pending" or None (not in ComfyUI's queue)."""
    q = _get(server, "/queue")
    if any(item[1] == prompt_id for item in q.get("queue_running", [])):
        return "running"
    if any(item[1] == prompt_id for item in q.get("queue_pending", [])):
        return "pending"
    return None


def wait(server, prompt_id, timeout=600, poll=1.0):
    """Wait for prompt_id's history record.

    `timeout` counts from when the job starts running: time spent waiting in
    the queue behind other jobs never times out. If the job leaves the queue
    without a result (e.g. deleted in ComfyUI's own UI), raise instead of
    waiting forever. On timeout the job is cancelled so it doesn't run orphaned.
    """
    deadline, missing = None, 0
    while True:
        _check_cancelled(prompt_id)
        try:
            hist = _get(server, f"/history/{prompt_id}")
            if prompt_id in hist:
                return hist[prompt_id]
            state = _queue_state(server, prompt_id)
        except urllib.error.URLError as e:
            raise ComfyError(f"Lost contact with ComfyUI: {e.reason}") from e
        if state == "running" and deadline is None:
            deadline = time.time() + timeout
        missing = missing + 1 if state is None else 0
        if missing >= 5:  # gone from the queue with no history for ~5 s
            raise ComfyError(f"Job {prompt_id} left ComfyUI's queue without a result.")
        if deadline is not None and time.time() > deadline:
            try:
                cancel(server, prompt_id)
            except ComfyError:
                pass
            _cancelled.discard(prompt_id)
            raise ComfyError(f"Job {prompt_id} ran longer than {timeout}s and was stopped.")
        time.sleep(poll)


def collect_images(server, record):
    """Download every SaveImage output from a finished history record."""
    images = []
    for node in record.get("outputs", {}).values():
        for img in node.get("images", []):
            query = urllib.parse.urlencode(img)
            with urllib.request.urlopen(f"{server}/view?{query}") as r:
                images.append((img["filename"], r.read()))
    return images


def generate(server, *, timeout=600, on_progress=None, **params):
    """Full round trip: patch graph, queue, wait, fetch images.

    `on_progress(dict)` is called with {"state": "queued"|"running", "value",
    "max"} as ComfyUI reports sampler steps. Returns
    {"prompt_id", "seed", "images": [(filename, png_bytes), ...]}.
    """
    return _run(server, *build_workflow(**params), timeout=timeout,
                on_progress=on_progress)


def edit(server, image_name, image_data, *, timeout=600, on_progress=None, **params):
    """Upload a photo, then run the edit graph on it with the given instruction.

    Same arguments and return shape as generate().
    """
    stored = upload_image(server, _unique(image_name), image_data)
    return _run(server, *build_edit_workflow(image=stored, **params), timeout=timeout,
                on_progress=on_progress)


def inpaint(server, image_name, image_data, mask_data, *, reference_data=None,
            timeout=600, on_progress=None, **params):
    """Upload a photo and its mask (and optional reference photo), then
    regenerate only the masked area.

    Same arguments and return shape as generate().
    """
    stem = Path(_unique(image_name)).stem
    image = upload_image(server, f"{stem}.png", image_data)
    mask = upload_image(server, f"{stem}_mask.png", mask_data)
    reference = (upload_image(server, f"{stem}_ref.png", reference_data)
                 if reference_data else None)
    return _run(server, *build_inpaint_workflow(image=image, mask=mask,
                                                reference=reference, **params),
                timeout=timeout, on_progress=on_progress)


def _open_ws(server, client_id):
    """Connect to ComfyUI's event websocket, or return None if unavailable."""
    if websocket is None:
        return None
    url = server.replace("http", "ws", 1) + f"/ws?clientId={client_id}"
    try:
        return websocket.create_connection(url, timeout=5)
    except Exception:
        return None


def _watch(server, ws, prompt_id, timeout, on_progress):
    """Relay progress events for prompt_id until it finishes or fails.

    Returns early (and leaves the verdict to wait()) if the job runs past
    `timeout` once started, or drops out of the queue while still pending.
    """
    deadline, quiet = None, 0
    ws.settimeout(5)
    while deadline is None or time.time() < deadline:
        if prompt_id in _cancelled:
            return  # wait() raises Cancelled
        try:
            msg = ws.recv()
        except websocket.WebSocketTimeoutException:
            quiet += 1
            if deadline is None and quiet % 6 == 0:  # every ~30 s while queued
                try:
                    if _queue_state(server, prompt_id) is None:
                        return  # finished or removed: wait() sorts it out
                except Exception:
                    return
            continue
        except Exception:
            return  # lost the socket: fall back to polling /history
        if not isinstance(msg, str):
            continue  # binary latent previews
        event = json.loads(msg)
        data = event.get("data", {})
        if data.get("prompt_id") != prompt_id:
            continue
        kind = event.get("type")
        if kind == "executing":
            if data.get("node") is None:
                return
            if deadline is None:
                deadline = time.time() + timeout
            on_progress({"state": "running"})
        elif kind == "progress":
            on_progress({"state": "running", "value": data["value"], "max": data["max"]})
        elif kind in ("execution_success", "execution_error", "execution_interrupted"):
            return


def _run(server, wf, seed, *, timeout, on_progress=None):
    client_id = uuid.uuid4().hex
    ws = _open_ws(server, client_id) if on_progress else None
    try:
        prompt_id = queue(server, wf, client_id)
        if ws:
            report = lambda event: on_progress({**event, "prompt_id": prompt_id})
            report({"state": "queued"})
            _watch(server, ws, prompt_id, timeout, report)
    finally:
        if ws:
            ws.close()
    record = wait(server, prompt_id, timeout=timeout)
    return {
        "prompt_id": prompt_id,
        "seed": seed,
        "images": collect_images(server, record),
    }
