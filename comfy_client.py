"""Minimal ComfyUI client for the AI Visual Workshop workflows.

Queues the API-format graph (text-to-image, image edit, masked inpaint of an
uploaded photo, or a Wan 2.2 video) on a running ComfyUI server, waits for the job
to finish and pulls the rendered images or video back out. Standard library only.
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
VIDEO_WORKFLOW = WORKFLOWS / "wan2.2_ti2v_5b_gguf_api.json"
POSE_WORKFLOW = WORKFLOWS / "qwen_image_2.1_gguf_pose_api.json"
UPSCALE_WORKFLOW = WORKFLOWS / "upscale_api.json"
BG_REMOVE_WORKFLOW = WORKFLOWS / "bg_remove_api.json"
BG_REPLACE_WORKFLOW = WORKFLOWS / "qwen_image_2.1_gguf_bg_replace_api.json"
VIDEO_BG_WORKFLOW = WORKFLOWS / "video_bg_remove_api.json"
VIDEO_SMOOTH_WORKFLOW = WORKFLOWS / "video_smooth_api.json"
BG_MODEL = "birefnet.safetensors"
INTERP_MODEL = "rife_v4.26.safetensors"
# Prompt wrappers: the user only describes the new background / the light.
BG_PROMPT = ("Replace the background with: {prompt}. Keep the person or subject exactly as it is, "
             "and match the new background's lighting, perspective and focus to the subject.")
RELIGHT_PROMPT = ("Relight this photo: {prompt}. Change only the lighting, light direction, colour "
                  "and shadows; keep the people, faces, pose, clothing, objects and composition "
                  "exactly the same.")
# Video background colours (0xRRGGBB) by name.
BG_COLORS = {"green": 0x00B140, "black": 0x000000, "white": 0xFFFFFF, "blue": 0x0047BB}
UPSCALE_MODEL = "4x-UltraSharpV2.safetensors"  # a 4x model; smaller factors scale its output down
# Wraps the user's prompt for the pose graph: image 1 is the SDPose skeleton, not a picture.
POSE_PROMPT = ("Image 1 is a pose skeleton map (OpenPose-style keypoints on black). Create a new, "
               "fully rendered image in which the person takes exactly this pose: same body, arm, "
               "leg and head positions, same framing. Do not draw the skeleton, lines or dots. "
               "The image: {prompt}")
CHROMA_WORKFLOW = WORKFLOWS / "chroma1_hd_gguf_t2i_api.json"
SDXL_WORKFLOW = WORKFLOWS / "sdxl_t2i_api.json"
FACE_VIDEO_WORKFLOW = WORKFLOWS / "wan2.2_i2v_a14b_face_test_gguf_api.json"
# Text-to-image model families: "qwen" (Qwen-Image 2.1), "krea2" (Krea 2 Turbo),
# "chroma" (Chroma1-HD) or "sdxl" (any SDXL checkpoint, e.g. RealVisXL Lightning).
T2I_WORKFLOWS = {"qwen": WORKFLOW, "krea2": KREA2_WORKFLOW,
                 "chroma": CHROMA_WORKFLOW, "sdxl": SDXL_WORKFLOW}
MAX_SEED = 2 ** 53


class ComfyError(RuntimeError):
    """Raised when ComfyUI is unreachable, rejects the graph or times out."""


class Cancelled(ComfyError):
    """Raised when a job is cancelled with cancel()."""


_cancelled = set()  # prompt_ids cancelled while a caller is still waiting on them


def load_workflow(path=WORKFLOW):
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_lora(wf, lora, strength, consumer="6"):
    """Insert a LoraLoaderModelOnly between the model loader ("1") and the node
    that takes the model (`consumer`: the sampler, or Wan's ModelSamplingSD3)."""
    if not lora:
        return
    wf["20"] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {"model": ["1", 0], "lora_name": lora,
                   "strength_model": float(strength)},
    }
    wf[consumer]["inputs"]["model"] = ["20", 0]


def build_workflow(prompt, *, model="qwen", negative="", width=1024, height=1024,
                   steps=25, cfg=1.0, seed=None, batch=1, unet=None, clip=None,
                   lora=None, lora_strength=1.0,
                   sampler=None, scheduler=None, prefix=None):
    """Patch the text-to-image graph for `model` (a T2I_WORKFLOWS key).

    Krea 2 Turbo is distilled: use about 8 steps and cfg 1 (it has no negative
    prompt). For "sdxl", `unet` is the checkpoint file. `sampler`/`scheduler`
    default to the graph's own (each model has its own best pair).
    Returns (workflow_dict, resolved_seed).
    """
    if model not in T2I_WORKFLOWS:
        raise ValueError(f"unknown model {model!r}; expected one of {sorted(T2I_WORKFLOWS)}")
    wf = load_workflow(T2I_WORKFLOWS[model])
    if unet:
        wf["1"]["inputs"]["ckpt_name" if model == "sdxl" else "unet_name"] = unet
    if clip and "2" in wf:
        wf["2"]["inputs"]["clip_name"] = clip
    if model == "qwen":
        wf["4"]["inputs"]["prompt"] = prompt
        wf["4"]["inputs"]["negative_prompt"] = negative
    else:
        wf["4"]["inputs"]["text"] = prompt
        if negative and model in ("chroma", "sdxl"):
            wf["9"]["inputs"]["text"] = negative
    _apply_lora(wf, lora, lora_strength)
    wf["5"]["inputs"].update(width=int(width), height=int(height),
                             batch_size=int(batch))
    seed = int(seed) if seed not in (None, "") else random.randint(0, MAX_SEED)
    wf["6"]["inputs"].update(seed=seed, steps=int(steps), cfg=float(cfg))
    if sampler:
        wf["6"]["inputs"]["sampler_name"] = sampler
    if scheduler:
        wf["6"]["inputs"]["scheduler"] = scheduler
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


def build_video_workflow(prompt, image=None, *, negative="", width=832, height=480,
                         frames=49, fps=24, steps=20, cfg=5.0, shift=8.0, seed=None,
                         unet=None, clip=None, lora=None, lora_strength=1.0,
                         sampler="uni_pc", scheduler="simple", prefix="video/Wan2.2_ti2v"):
    """Patch the Wan 2.2 TI2V-5B graph. `image` (a filename already uploaded to
    ComfyUI) is the first frame; without it the video comes from the prompt alone.

    width/height are multiples of 32 and `frames` is 4n+1 (49 = 2 s at 24 fps,
    121 = 5 s). Returns (workflow_dict, resolved_seed).
    """
    width, height, frames = int(width), int(height), int(frames)
    if width % 32 or height % 32:
        raise ValueError("width and height must be multiples of 32")
    if frames < 5 or (frames - 1) % 4:
        raise ValueError("frames must be 4n+1 (e.g. 49, 81, 121)")
    wf = load_workflow(VIDEO_WORKFLOW)
    if unet:
        wf["1"]["inputs"]["unet_name"] = unet
    if clip:
        wf["2"]["inputs"]["clip_name"] = clip
    wf["4"]["inputs"]["shift"] = float(shift)
    wf["5"]["inputs"]["text"] = prompt
    if negative:
        wf["6"]["inputs"]["text"] = negative
    _apply_lora(wf, lora, lora_strength, consumer="4")
    wf["8"]["inputs"].update(width=width, height=height, length=frames)
    if image:
        wf["7"]["inputs"]["image"] = image
    else:
        del wf["7"], wf["8"]["inputs"]["start_image"]
    seed = int(seed) if seed not in (None, "") else random.randint(0, MAX_SEED)
    wf["9"]["inputs"].update(seed=seed, steps=int(steps), cfg=float(cfg),
                             sampler_name=sampler, scheduler=scheduler)
    wf["11"]["inputs"]["fps"] = float(fps)
    wf["12"]["inputs"]["filename_prefix"] = prefix
    return wf, seed


def build_face_video_workflow(prompt, image, *, negative="", width=832, height=480,
                              frames=81, fps=16, steps=4, cfg=1.0, shift=5.0, seed=None,
                              unet=None, clip=None, lora=None, lora_strength=1.0,
                              sampler="euler", scheduler="simple",
                              prefix="video/Wan2.2_i2v_face_test"):
    """(test) Patch the Wan 2.2 I2V-A14B graph (LightX2V 4-step distill): photo to
    video, strongest on faces. Two experts share the steps: high-noise for the first
    half, low-noise for the rest. `unet` is the high-noise file; the low-noise file
    is the same name with "high_noise" -> "low_noise". `image` is required.
    Returns (workflow_dict, resolved_seed).
    """
    if not image:
        raise ValueError("the face video model needs a start photo")
    width, height, frames, steps = int(width), int(height), int(frames), int(steps)
    if width % 16 or height % 16:
        raise ValueError("width and height must be multiples of 16")
    if frames < 5 or (frames - 1) % 4:
        raise ValueError("frames must be 4n+1 (e.g. 49, 81)")
    wf = load_workflow(FACE_VIDEO_WORKFLOW)
    if unet:
        wf["1"]["inputs"]["unet_name"] = unet
        wf["21"]["inputs"]["unet_name"] = unet.replace("high_noise", "low_noise")
    if clip:
        wf["2"]["inputs"]["clip_name"] = clip
    for node in ("4", "24"):
        wf[node]["inputs"]["shift"] = float(shift)
    if lora:  # the same LoRA on both experts
        for loader, sampling, node in (("1", "4", "20"), ("21", "24", "25")):
            wf[node] = {"class_type": "LoraLoaderModelOnly",
                        "inputs": {"model": [loader, 0], "lora_name": lora,
                                   "strength_model": float(lora_strength)}}
            wf[sampling]["inputs"]["model"] = [node, 0]
    wf["5"]["inputs"]["text"] = prompt
    if negative:
        wf["6"]["inputs"]["text"] = negative
    wf["7"]["inputs"]["image"] = image
    wf["8"]["inputs"].update(width=width, height=height, length=frames)
    seed = int(seed) if seed not in (None, "") else random.randint(0, MAX_SEED)
    split = max(1, steps // 2)
    for node, start, end in (("9", 0, split), ("29", split, 10000)):
        wf[node]["inputs"].update(noise_seed=seed, steps=steps, cfg=float(cfg),
                                  sampler_name=sampler, scheduler=scheduler,
                                  start_at_step=start, end_at_step=end)
    wf["11"]["inputs"]["fps"] = float(fps)
    wf["12"]["inputs"]["filename_prefix"] = prefix
    return wf, seed


def build_pose_workflow(prompt, image, *, negative="", resolution=1024, steps=25,
                        cfg=1.0, seed=None, unet=None, clip=None,
                        lora=None, lora_strength=1.0,
                        sampler="euler", scheduler="simple",
                        prefix="Qwen_image_2.1_gguf_pose"):
    """Patch the pose graph: SDPose reads the pose of the person in `image` (a filename
    already uploaded to ComfyUI) and Qwen-Image draws `prompt` in that pose. The skeleton
    map is saved too. Returns (workflow_dict, resolved_seed).
    """
    wf = load_workflow(POSE_WORKFLOW)
    if unet:
        wf["1"]["inputs"]["unet_name"] = unet
    if clip:
        wf["2"]["inputs"]["clip_name"] = clip
    wf["4"]["inputs"].update(prompt=POSE_PROMPT.format(prompt=prompt), negative_prompt=negative,
                             resolution=int(resolution))
    _apply_lora(wf, lora, lora_strength)
    seed = int(seed) if seed not in (None, "") else random.randint(0, MAX_SEED)
    wf["6"]["inputs"].update(seed=seed, steps=int(steps), cfg=float(cfg),
                             sampler_name=sampler, scheduler=scheduler)
    wf["8"]["inputs"]["filename_prefix"] = prefix
    wf["9"]["inputs"]["image"] = image
    wf["31"]["inputs"]["resize_type.longer_size"] = int(resolution)
    return wf, seed


def build_bg_remove_workflow(image, *, model=BG_MODEL, prefix="cutout"):
    """Cut the subject out of `image` (an uploaded filename) as a transparent PNG.
    Returns (workflow, None)."""
    wf = load_workflow(BG_REMOVE_WORKFLOW)
    wf["1"]["inputs"]["image"] = image
    wf["2"]["inputs"]["bg_removal_name"] = model
    wf["6"]["inputs"]["filename_prefix"] = prefix
    return wf, None


def build_bg_replace_workflow(prompt, image, *, negative="", steps=25, cfg=1.0, seed=None,
                              unet=None, clip=None, lora=None, lora_strength=1.0,
                              model=BG_MODEL, grow=3, prefix="Qwen_image_2.1_gguf_background"):
    """Keep the subject of `image` (an uploaded filename, multiples of 32) and let
    Qwen-Image paint a new background from `prompt`: BiRefNet finds the subject, and
    everything else is inpainted. Returns (workflow_dict, resolved_seed)."""
    wf = load_workflow(BG_REPLACE_WORKFLOW)
    if unet:
        wf["1"]["inputs"]["unet_name"] = unet
    if clip:
        wf["2"]["inputs"]["clip_name"] = clip
    wf["4"]["inputs"].update(prompt=BG_PROMPT.format(prompt=prompt), negative_prompt=negative)
    _apply_lora(wf, lora, lora_strength)
    seed = int(seed) if seed not in (None, "") else random.randint(0, MAX_SEED)
    wf["6"]["inputs"].update(seed=seed, steps=int(steps), cfg=float(cfg))
    wf["8"]["inputs"]["filename_prefix"] = prefix
    wf["9"]["inputs"]["image"] = image
    wf["30"]["inputs"]["bg_removal_name"] = model
    wf["33"]["inputs"]["expand"] = int(grow)
    return wf, seed


def build_video_fx_workflow(video, *, effect="smooth", multiplier=2, color="green",
                            bg_model=BG_MODEL, interp_model=INTERP_MODEL):
    """Patch a video effect graph for `video` (an uploaded filename): "smooth" adds
    in-between frames with RIFE (`multiplier` x the frame rate), "remove_bg" puts
    the subject on a plain `color` background. Returns (workflow, None)."""
    if effect == "smooth":
        multiplier = int(multiplier)
        if not 2 <= multiplier <= 4:
            raise ValueError("multiplier must be 2, 3 or 4")
        wf = load_workflow(VIDEO_SMOOTH_WORKFLOW)
        wf["3"]["inputs"]["model_name"] = interp_model
        wf["4"]["inputs"]["multiplier"] = multiplier
        wf["5"]["inputs"]["values.b"] = multiplier
    elif effect == "remove_bg":
        if color not in BG_COLORS:
            raise ValueError(f"color must be one of {sorted(BG_COLORS)}")
        wf = load_workflow(VIDEO_BG_WORKFLOW)
        wf["3"]["inputs"]["bg_removal_name"] = bg_model
        wf["6"]["inputs"]["color"] = BG_COLORS[color]
    else:
        raise ValueError("effect must be 'smooth' or 'remove_bg'")
    wf["1"]["inputs"]["file"] = video
    return wf, None


def build_upscale_workflow(image, *, scale=2, model=UPSCALE_MODEL, prefix="upscale"):
    """Patch the upscale graph: `image` (an uploaded filename) through the 4x model,
    then scaled down to `scale` (2 or 4) times the original. Returns (workflow, None)."""
    scale = float(scale)
    if not 1 <= scale <= 4:
        raise ValueError("scale must be between 1 and 4")
    wf = load_workflow(UPSCALE_WORKFLOW)
    wf["1"]["inputs"]["image"] = image
    wf["2"]["inputs"]["model_name"] = model
    if scale == 4:
        del wf["4"]
        wf["5"]["inputs"]["images"] = ["3", 0]
    else:
        wf["4"]["inputs"]["scale_by"] = scale / 4
    wf["5"]["inputs"]["filename_prefix"] = prefix
    return wf, None


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
        raise ComfyError(_missing_model(detail) or
                         f"ComfyUI rejected the workflow ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise ComfyError(f"Cannot reach ComfyUI at {server}: {e.reason}") from e


def _missing_model(detail):
    """A readable message when ComfyUI rejects a graph because a model file isn't in
    its list (not downloaded, or ComfyUI not restarted since its folder was added)."""
    try:
        errors = json.loads(detail).get("node_errors", {})
    except (ValueError, AttributeError):
        return None
    for node in errors.values():
        for err in node.get("errors", []):
            info = err.get("extra_info", {})
            if err.get("type") == "value_not_in_list" and "name" in info.get("input_name", ""):
                return (f"ComfyUI can't find the model {info.get('received_value')!r} "
                        f"({node.get('class_type')}). Download it (see the README), or restart "
                        "ComfyUI if you've just added it or its folder.")
    return None


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
    """Download every SaveImage / SaveVideo output from a finished history record
    (ComfyUI lists saved videos under "images" too, and some nodes use "gifs")."""
    images = []
    for node in record.get("outputs", {}).values():
        for img in node.get("images", []) + node.get("gifs", []) + node.get("videos", []):
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


def video(server, image_name=None, image_data=None, *, model="wan", timeout=7200,
          on_progress=None, **params):
    """Upload the start photo (if any), then render a Wan 2.2 video: `model` "wan"
    (TI2V-5B) or "wanface" (I2V-A14B, test; needs the photo).

    Same return shape as generate(); "images" holds the .mp4.
    """
    build = build_face_video_workflow if model == "wanface" else build_video_workflow
    if model == "wanface" and not image_data:
        raise ValueError("the face video model (test) needs a start photo")
    stored = upload_image(server, _unique(image_name), image_data) if image_data else None
    return _run(server, *build(image=stored, **params), timeout=timeout,
                on_progress=on_progress)


def pose(server, image_name, image_data, *, timeout=600, on_progress=None, **params):
    """Upload the pose photo, then draw the prompt in the pose found in it.

    Same arguments and return shape as generate(); "images" holds the result and
    the skeleton map.
    """
    stored = upload_image(server, _unique(image_name), image_data)
    return _run(server, *build_pose_workflow(image=stored, **params), timeout=timeout,
                on_progress=on_progress)


def background(server, image_name, image_data, *, mode="remove", timeout=1800,
               on_progress=None, **params):
    """Upload a photo, then cut out its subject ("remove": transparent PNG) or give it
    a new background from `prompt` ("replace")."""
    stored = upload_image(server, _unique(image_name), image_data)
    if mode == "replace":
        built = build_bg_replace_workflow(image=stored, **params)
    else:
        built = build_bg_remove_workflow(stored)
    return _run(server, *built, timeout=timeout, on_progress=on_progress)


def video_fx(server, video_name, video_data, *, timeout=3600, on_progress=None, **params):
    """Upload a video and run a video effect on it (see build_video_fx_workflow)."""
    stored = upload_image(server, _unique(video_name), video_data)
    return _run(server, *build_video_fx_workflow(stored, **params), timeout=timeout,
                on_progress=on_progress)


def upscale(server, image_name, image_data, *, timeout=1800, on_progress=None, **params):
    """Upload a photo and enlarge it 2x or 4x with the upscale model."""
    stored = upload_image(server, _unique(image_name), image_data)
    return _run(server, *build_upscale_workflow(image=stored, **params), timeout=timeout,
                on_progress=on_progress)


# What the job is doing while ComfyUI runs a node of this class (shown on the job card).
_PHASES = {
    "UnetLoaderGGUF": "Loading models", "CLIPLoader": "Loading models",
    "CLIPLoaderGGUF": "Loading models", "VAELoader": "Loading models",
    "LoraLoaderModelOnly": "Loading models", "ModelSamplingSD3": "Loading models",
    "LoadImage": "Loading the photo", "LoadImageMask": "Loading the photo",
    "CLIPTextEncode": "Encoding the prompt", "TextEncodeQwenImage21": "Encoding the prompt",
    "ConditioningZeroOut": "Encoding the prompt",
    "VAEEncode": "Encoding the photo", "Wan22ImageToVideoLatent": "Encoding the photo",
    "KSampler": "Sampling", "KSamplerAdvanced": "Sampling",
    "T5TokenizerOptions": "Encoding the prompt", "ModelSamplingAuraFlow": "Loading models",
    "WanImageToVideo": "Encoding the photo",
    "VAEDecode": "Decoding", "ImageCompositeMasked": "Blending into the photo",
    "CheckpointLoaderSimple": "Loading models", "UpscaleModelLoader": "Loading models",
    "ResizeImageMaskNode": "Loading the photo",
    "SDPoseKeypointExtractor": "Finding the pose", "SDPoseDrawKeypoints": "Finding the pose",
    "ImageUpscaleWithModel": "Upscaling", "ImageScaleBy": "Upscaling",
    "LoadBackgroundRemovalModel": "Loading models", "FrameInterpolationModelLoader": "Loading models",
    "RemoveBackground": "Finding the subject", "FrameInterpolate": "Adding in-between frames",
    "LoadVideo": "Loading the video", "GetVideoComponents": "Loading the video",
    "JoinImageWithAlpha": "Cutting out",
    "CreateVideo": "Saving", "SaveVideo": "Saving", "SaveImage": "Saving",
}


def _phases(wf):
    """Node id -> phase label for a workflow (video graphs decode frames, not an image)."""
    video = any(n["class_type"] == "SaveVideo" for n in wf.values())
    phases = {}
    for nid, node in wf.items():
        phase = _PHASES.get(node["class_type"], "Working")
        if phase == "Decoding":
            phase = "Decoding the video frames" if video else "Decoding the image"
        phases[nid] = phase
    return phases


def _open_ws(server, client_id):
    """Connect to ComfyUI's event websocket, or return None if unavailable."""
    if websocket is None:
        return None
    url = server.replace("http", "ws", 1) + f"/ws?clientId={client_id}"
    try:
        return websocket.create_connection(url, timeout=5)
    except Exception:
        return None


def _watch(server, ws, prompt_id, timeout, on_progress, phases):
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
            on_progress({"state": "running", "phase": phases.get(str(data["node"]), "Working")})
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
            _watch(server, ws, prompt_id, timeout, report, _phases(wf))
    finally:
        if ws:
            ws.close()
    record = wait(server, prompt_id, timeout=timeout)
    return {
        "prompt_id": prompt_id,
        "seed": seed,
        "images": collect_images(server, record),
    }
