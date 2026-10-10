"""Minimal ComfyUI client for the Qwen-Image 2.1 GGUF text-to-image workflow.

Queues the API-format graph on a running ComfyUI server, waits for the job to
finish and pulls the rendered images back out. Standard library only.
"""
import json
import random
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

WORKFLOW = Path(__file__).parent / "workflows" / "qwen_image_2.1_gguf_t2i_api.json"
MAX_SEED = 2 ** 53


class ComfyError(RuntimeError):
    """Raised when ComfyUI is unreachable, rejects the graph or times out."""


def load_workflow():
    return json.loads(WORKFLOW.read_text(encoding="utf-8"))


def build_workflow(prompt, *, negative="", width=1024, height=1024, steps=25,
                   cfg=1.0, seed=None, batch=1, unet=None, clip=None,
                   sampler="euler", scheduler="simple",
                   prefix="Qwen_image_2.1_gguf"):
    """Patch the template graph with the requested parameters.

    Returns (workflow_dict, resolved_seed).
    """
    wf = load_workflow()
    if unet:
        wf["1"]["inputs"]["unet_name"] = unet
    if clip:
        wf["2"]["inputs"]["clip_name"] = clip
    wf["4"]["inputs"]["prompt"] = prompt
    wf["4"]["inputs"]["negative_prompt"] = negative
    wf["5"]["inputs"].update(width=int(width), height=int(height),
                             batch_size=int(batch))
    seed = int(seed) if seed not in (None, "") else random.randint(0, MAX_SEED)
    wf["6"]["inputs"].update(seed=seed, steps=int(steps), cfg=float(cfg),
                             sampler_name=sampler, scheduler=scheduler)
    wf["8"]["inputs"]["filename_prefix"] = prefix
    return wf, seed


def _get(server, path, timeout=10):
    with urllib.request.urlopen(f"{server}{path}", timeout=timeout) as r:
        return json.load(r)


def ping(server, timeout=3):
    """Return True if a ComfyUI server answers at `server`."""
    try:
        _get(server, "/system_stats", timeout=timeout)
        return True
    except Exception:
        return False


def queue(server, wf, client_id):
    data = json.dumps({"prompt": wf, "client_id": client_id}).encode()
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


def wait(server, prompt_id, timeout=600, poll=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            hist = _get(server, f"/history/{prompt_id}")
        except urllib.error.URLError as e:
            raise ComfyError(f"Lost contact with ComfyUI: {e.reason}") from e
        if prompt_id in hist:
            return hist[prompt_id]
        time.sleep(poll)
    raise ComfyError(f"Timed out after {timeout}s waiting for job {prompt_id}")


def collect_images(server, record):
    """Download every SaveImage output from a finished history record."""
    images = []
    for node in record.get("outputs", {}).values():
        for img in node.get("images", []):
            query = urllib.parse.urlencode(img)
            with urllib.request.urlopen(f"{server}/view?{query}") as r:
                images.append((img["filename"], r.read()))
    return images


def generate(server, *, timeout=600, **params):
    """Full round trip: patch graph, queue, wait, fetch images.

    Returns {"prompt_id", "seed", "images": [(filename, png_bytes), ...]}.
    """
    wf, seed = build_workflow(**params)
    client_id = uuid.uuid4().hex
    prompt_id = queue(server, wf, client_id)
    record = wait(server, prompt_id, timeout=timeout)
    return {
        "prompt_id": prompt_id,
        "seed": seed,
        "images": collect_images(server, record),
    }
