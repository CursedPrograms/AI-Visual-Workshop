"""Flask server for AI Visual Workshop.

A web UI and JSON API over the ComfyUI text-to-image, image-edit, inpaint and
video workflows in this repo.
ComfyUI must be running separately (see the README); this server talks to it
over HTTP, so point COMFY_SERVER at it if it is not on the default port.

    python app.py                 # http://127.0.0.1:7870
    COMFY_SERVER=http://host:8188 python app.py
"""
import base64
import json
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import comfy_client
import model_manager
import prompt_helper

BASE = Path(__file__).parent
OUTPUT_DIR = BASE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

with (BASE / "config.json").open(encoding="utf-8") as fh:
    CONFIG = json.load(fh)["Config"]

COMFY_SERVER = os.environ.get("COMFY_SERVER", "http://127.0.0.1:8188").rstrip("/")

# Text-to-image model families and the published files offered in the UI
# dropdowns (first = default). Edit and inpaint always use Qwen-Image 2.1.
MODELS = {
    "qwen": {
        "label": "Qwen-Image 2.1",
        "about": {"text": "The all-rounder: follows long prompts closely and renders readable text in images. Uncensored build.",
                  "best": "Detailed scenes, text and signs, illustrations, photos", "speed": "~25 steps · slowest, best prompt following",
                  "license": "Qwen Research License"},
        "steps": 25,
        "unets": [
            "qwen-image-2.1-UC-Q4_K_M.gguf",
            "qwen-image-2.1-UC-Q4_0.gguf",
            "qwen-image-2.1-UC-Q5_K_M.gguf",
            "qwen-image-2.1-UC-Q6_K.gguf",
            "qwen-image-2.1-UC-Q8_0.gguf",
            "qwen-image-2.1-UC-BF16.gguf",
        ],
        "clips": [
            "qwen3vl_8b_int8_convrot.safetensors",
            "qwen3vl_8b_bf16.safetensors",
        ],
    },
    "krea2": {
        "label": "Krea 2 Turbo",
        "about": {"text": "A distilled 12B model with a strong photographic, aesthetic look. No negative prompt.",
                  "best": "Photos, cinematic shots, quick ideas", "speed": "8 steps · fast",
                  "license": "Krea 2 Community License"},
        "steps": 8,
        "unets": [
            "krea2_turbo_bf16-Q4_0.gguf",
            "krea2_turbo_bf16-Q4_1.gguf",
            "krea2_turbo_bf16-Q5_0.gguf",
            "krea2_turbo_bf16-Q8_0.gguf",
        ],
        "clips": [
            "qwen3vl_4b_fp8_scaled.safetensors",
            "qwen3vl_4b_bf16.safetensors",
        ],
    },
    "sdxl": {
        "label": "SDXL",
        "about": {"text": "Classic SDXL checkpoints. RealVisXL Lightning is photoreal and uncensored; NoobAI-XL is anime; Juggernaut is cinematic.",
                  "best": "Fast photoreal people and portraits, huge LoRA ecosystem", "speed": "6 steps (Lightning) · fastest",
                  "license": "Per checkpoint (RealVisXL: OpenRAIL++)"},
        "steps": 6,
        "cfg": 1.5,
        # checkpoints (model + encoders + VAE in one file); per-file step/CFG defaults
        "unets": [
            "RealVisXL_V5.0_Lightning_fp16.safetensors",
            "NoobAI-XL-v1.1.safetensors",
            "Juggernaut-XI-byRunDiffusion.safetensors",
        ],
        "presets": {
            "NoobAI-XL-v1.1.safetensors": {"steps": 25, "cfg": 5},
            "Juggernaut-XI-byRunDiffusion.safetensors": {"steps": 25, "cfg": 5},
        },
        "clips": [],
    },
    "chroma": {
        "label": "Chroma1-HD",
        "about": {"text": "An uncensored 8.9B Flux-based model trained from scratch on a broad, unfiltered set. Strong on photos and art.",
                  "best": "Uncensored photos and art, varied styles", "speed": "~26 steps · medium",
                  "license": "Apache 2.0"},
        "steps": 26,
        "cfg": 3.5,
        "unets": [
            "Chroma1-HD-Q4_K_M.gguf",
            "Chroma1-HD-Q5_K_M.gguf",
            "Chroma1-HD-Q8_0.gguf",
        ],
        "clips": [
            "t5xxl_fp8_e4m3fn_scaled.safetensors",
            "t5xxl_fp16.safetensors",
        ],
    },
}
# Which Models-page entries provide each family (any one is enough).
FAMILY_MODELS = {"qwen": ["qwen"], "krea2": ["krea2"], "sdxl": ["realvis", "noobai", "juggernaut"],
                 "chroma": ["chroma"], "wan": ["wan"], "wanface": ["wanface"]}

# Video: Wan 2.2 TI2V-5B (text-to-video, or image-to-video from a start photo).
VIDEO = {
    "label": "Wan 2.2 TI2V-5B",
        "about": {"text": "Video from a prompt alone, or bring a start photo to life. 24 fps.",
                  "best": "Scenes, motion, text-to-video", "speed": "20 steps · ~4 min for 2 s on a 6 GB card",
                  "license": "Apache 2.0"},
    "steps": 20,
    "cfg": 5.0,
    "unets": [
        "Wan2.2-TI2V-5B-Q5_K_M.gguf",
        "Wan2.2-TI2V-5B-Q4_K_M.gguf",
        "Wan2.2-TI2V-5B-Q6_K.gguf",
        "Wan2.2-TI2V-5B-Q8_0.gguf",
    ],
    "clips": [
        "umt5-xxl-encoder-Q5_K_M.gguf",
        "umt5-xxl-encoder-Q8_0.gguf",
    ],
    "fps": 24,
}
# (test) Wan 2.2 I2V-A14B, LightX2V 4-step: photo to video, strongest on faces.
# `unets` are the high-noise files; the low-noise twin is picked by name.
VIDEO_FACE = {
    "label": "Wan 2.2 I2V-A14B · faces (test)",
        "about": {"text": "(test) The big 14B image-to-video model, split into two experts. Keeps faces and identity far better than the 5B. Needs a start photo.",
                  "best": "Portraits and people from a photo: expressions, head turns, talking", "speed": "4 steps (LightX2V) · 16 fps · heavy on 6 GB",
                  "license": "Apache 2.0"},
    "steps": 4,
    "cfg": 1.0,
    "fps": 16,
    "unets": [
        "wan2.2_i2v_A14b_high_noise_lightx2v_4step_720p_260412-Q3_K_M.gguf",
        "wan2.2_i2v_A14b_high_noise_lightx2v_4step_720p_260412-Q4_K_S.gguf",
        "wan2.2_i2v_A14b_high_noise_lightx2v_4step_720p_260412-Q4_K_M.gguf",
    ],
    "clips": VIDEO["clips"],
}
VIDEO_NEGATIVE = (
    "blurry, low quality, worst quality, jpeg artifacts, static, frozen frame, overexposed, "
    "deformed, distorted face, extra fingers, malformed hands, bad anatomy, watermark, text, subtitles"
)

app = Flask(__name__)

# Every job submitted with a `job` id, by id: kind, prompt, the browser that sent it
# (`client`), "state" (starting/queued/running/done/failed/cancelled), step progress and
# the result or error. Kept on the server so a page reopened later can pick its jobs up,
# and saved to output/jobs.json when a job ends, so the gallery survives a restart.
JOBS_FILE = OUTPUT_DIR / "jobs.json"
MAX_JOBS = 200
_jobs_lock = threading.Lock()


def _load_jobs():
    try:
        jobs = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    for rec in jobs.values():  # whatever was still running died with the old server
        if rec.get("state") not in ("done", "failed", "cancelled"):
            rec.update(state="failed", error="Interrupted: the server restarted.")
    return jobs


def _save_jobs():
    with _jobs_lock:
        tmp = JOBS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(JOBS), encoding="utf-8")
        tmp.replace(JOBS_FILE)


JOBS = _load_jobs()


def _run_job(kind, prompt, job, client, call):
    """Run call(on_progress) for one job, record how it ends under JOBS[job]
    and turn it into the endpoint's response."""
    rec = None
    if job:
        while len(JOBS) >= MAX_JOBS:  # drop the oldest
            JOBS.pop(next(iter(JOBS)))
        rec = JOBS[job] = {"id": job, "client": client or "", "kind": kind,
                           "prompt": prompt, "created": time.time(), "state": "starting"}
    def end(**fields):
        if rec:
            rec.update(fields)
            _save_jobs()
    try:
        result = call((lambda event: rec.update({"value": None, "max": None, **event})) if rec else None)
    except comfy_client.Cancelled:
        end(state="cancelled")
        return jsonify(error="Cancelled.", cancelled=True), 409
    except comfy_client.ComfyError as exc:
        end(state="failed", error=str(exc))
        return jsonify(error=str(exc)), 502
    except (ValueError, TypeError) as exc:
        end(state="failed", error=f"Bad parameter: {exc}")
        return jsonify(error=f"Bad parameter: {exc}"), 400
    body = _save(result)
    end(state="done", result=dict(body, images=[
        {k: v for k, v in img.items() if k != "data"} for img in body["images"]]))
    return jsonify(**body)


@app.route("/")
def index():
    have = model_manager.installed_ids(COMFY_SERVER)  # None when ComfyUI is down
    families = dict(MODELS, wan=VIDEO, wanface=VIDEO_FACE)
    families = {k: dict(v, installed=have is None or any(m in have for m in FAMILY_MODELS[k]))
                for k, v in families.items()}
    return render_template(
        "index.html",
        config=CONFIG,
        server=COMFY_SERVER,
        models={k: families[k] for k in MODELS},
        families=families,
        video_negative=VIDEO_NEGATIVE,
    )


@app.route("/api/models")
def models_status():
    """Every known model with its status (installed / partial / missing / downloading)."""
    return jsonify(model_manager.status(COMFY_SERVER))


@app.route("/api/models/<model_id>/download", methods=["POST"])
def models_download(model_id):
    if model_id not in model_manager.BY_ID:
        return jsonify(error=f"Unknown model {model_id!r}."), 404
    return jsonify(model_manager.download(model_id, COMFY_SERVER))


@app.route("/api/models/<model_id>/cancel", methods=["POST"])
def models_cancel(model_id):
    return jsonify(cancelled=model_manager.cancel(model_id))


@app.route("/api/health")
def health():
    up = comfy_client.ping(COMFY_SERVER)
    return jsonify(comfy="up" if up else "down", server=COMFY_SERVER), (200 if up else 503)


@app.route("/api/loras")
def loras():
    """LoRA files ComfyUI can see (its models/loras plus extra_model_paths)."""
    return jsonify(loras=comfy_client.list_models(COMFY_SERVER, "LoraLoaderModelOnly", "lora_name"))


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True, silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="A prompt is required."), 400

    model = data.get("model") or "qwen"
    if model not in MODELS:
        return jsonify(error=f"Unknown model {model!r}."), 400

    return _run_job("generate", prompt, data.get("job"), data.get("client"), lambda on_progress:
        comfy_client.generate(
            COMFY_SERVER,
            prompt=prompt,
            model=model,
            negative=(data.get("negative") or "").strip(),
            width=data.get("width", 1024),
            height=data.get("height", 1024),
            steps=data.get("steps", MODELS[model]["steps"]),
            cfg=data.get("cfg", 1.0),
            seed=data.get("seed"),
            batch=data.get("batch", 1),
            unet=data.get("unet") or None,
            clip=data.get("clip") or None,
            lora=data.get("lora") or None,
            lora_strength=data.get("lora_strength", 1.0),
            timeout=int(data.get("timeout", 1800)),
            on_progress=on_progress,
        ))


@app.route("/api/edit", methods=["POST"])
def edit():
    """Image-to-image: multipart form with an `image` file and an instruction."""
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify(error="An image file is required."), 400
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="An edit instruction is required."), 400
    f = request.form
    kind = "relight" if f.get("kind") == "relight" else "edit"
    instruction = comfy_client.RELIGHT_PROMPT.format(prompt=prompt) if kind == "relight" else prompt

    return _run_job(kind, prompt, f.get("job"), f.get("client"), lambda on_progress:
        comfy_client.edit(
            COMFY_SERVER,
            Path(upload.filename).name,
            upload.read(),
            prompt=instruction,
            prefix=f"Qwen_image_2.1_gguf_{kind}",
            negative=(f.get("negative") or "").strip(),
            resolution=f.get("resolution", 1024),
            steps=f.get("steps", 25),
            cfg=f.get("cfg", 1.0),
            seed=f.get("seed") or None,
            unet=f.get("unet") or None,
            clip=f.get("clip") or None,
            lora=f.get("lora") or None,
            lora_strength=f.get("lora_strength", 1.0),
            timeout=int(f.get("timeout", 3600)),
            on_progress=on_progress,
        ))


@app.route("/api/inpaint", methods=["POST"])
def inpaint():
    """Masked edit: multipart form with `image` and `mask` files (same size,
    multiples of 32; white = regenerate) and a prompt for the masked area.
    Optional `reference` file: the picture the model sees instead of `image`
    (Uncrop sends the unpadded photo here)."""
    upload, mask = request.files.get("image"), request.files.get("mask")
    if not upload or not upload.filename or not mask:
        return jsonify(error="An image and a mask are required."), 400
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="A prompt is required."), 400
    f = request.form

    kind = "uncrop" if f.get("kind") == "uncrop" else "inpaint"
    return _run_job(kind, prompt, f.get("job"), f.get("client"), lambda on_progress:
        comfy_client.inpaint(
            COMFY_SERVER,
            Path(upload.filename).name,
            upload.read(),
            mask.read(),
            reference_data=(request.files["reference"].read()
                            if request.files.get("reference") else None),
            prompt=prompt,
            negative=(f.get("negative") or "").strip(),
            steps=f.get("steps", 25),
            cfg=f.get("cfg", 1.0),
            denoise=f.get("denoise", 1.0),
            prefix=f"Qwen_image_2.1_gguf_{kind}",
            seed=f.get("seed") or None,
            unet=f.get("unet") or None,
            clip=f.get("clip") or None,
            lora=f.get("lora") or None,
            lora_strength=f.get("lora_strength", 1.0),
            timeout=int(f.get("timeout", 3600)),
            on_progress=on_progress,
        ))


@app.route("/api/video", methods=["POST"])
def video():
    """Wan 2.2 video: multipart form with a `prompt` (the motion / scene) and an
    optional `image` file as the first frame (without it: text-to-video).
    `width`/`height` are multiples of 32, `frames` is 4n+1 (49 = 2 s at 24 fps).
    `model=wanface` picks the I2V-A14B face model (test), which needs the image."""
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="Describe the video first."), 400
    upload = request.files.get("image")
    f = request.form
    face = f.get("model") == "wanface"
    if face and not (upload and upload.filename):
        return jsonify(error="The face video model (test) needs a start photo."), 400
    fam = VIDEO_FACE if face else VIDEO

    return _run_job("video", prompt, f.get("job"), f.get("client"), lambda on_progress:
        comfy_client.video(
            COMFY_SERVER,
            Path(upload.filename).name if upload and upload.filename else None,
            upload.read() if upload and upload.filename else None,
            prompt=prompt,
            model="wanface" if face else "wan",
            negative=(f.get("negative") or "").strip() or VIDEO_NEGATIVE,
            width=f.get("width", 832),
            height=f.get("height", 480),
            frames=f.get("frames", 49),
            fps=f.get("fps", fam["fps"]),
            steps=f.get("steps", fam["steps"]),
            cfg=f.get("cfg", fam["cfg"]),
            seed=f.get("seed") or None,
            unet=f.get("unet") or None,
            clip=f.get("clip") or None,
            lora=f.get("lora") or None,
            lora_strength=f.get("lora_strength", 1.0),
            timeout=int(f.get("timeout", 7200)),
            on_progress=on_progress,
        ))


@app.route("/api/pose", methods=["POST"])
def pose():
    """Pose control: multipart form with an `image` file showing a person in the pose to
    copy, and a prompt for the new picture. Returns the picture and the skeleton map."""
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify(error="A photo with the pose is required."), 400
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="Describe the new picture first."), 400
    f = request.form

    return _run_job("pose", prompt, f.get("job"), f.get("client"), lambda on_progress:
        comfy_client.pose(
            COMFY_SERVER,
            Path(upload.filename).name,
            upload.read(),
            prompt=prompt,
            negative=(f.get("negative") or "").strip(),
            resolution=f.get("resolution", 1024),
            steps=f.get("steps", 25),
            cfg=f.get("cfg", 1.0),
            seed=f.get("seed") or None,
            unet=f.get("unet") or None,
            clip=f.get("clip") or None,
            lora=f.get("lora") or None,
            lora_strength=f.get("lora_strength", 1.0),
            timeout=int(f.get("timeout", 3600)),
            on_progress=on_progress,
        ))


@app.route("/api/background", methods=["POST"])
def background():
    """Background: multipart form with an `image` file and `mode` = "remove" (transparent
    PNG cut-out) or "replace" (plus a `prompt` for the new background; send the image at
    multiples of 32)."""
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify(error="An image file is required."), 400
    f = request.form
    mode = "replace" if f.get("mode") == "replace" else "remove"
    prompt = (f.get("prompt") or "").strip()
    if mode == "replace" and not prompt:
        return jsonify(error="Describe the new background first."), 400
    name = Path(upload.filename).name
    params = {} if mode == "remove" else dict(
        prompt=prompt,
        negative=(f.get("negative") or "").strip(),
        steps=f.get("steps", 25),
        cfg=f.get("cfg", 1.0),
        seed=f.get("seed") or None,
        unet=f.get("unet") or None,
        clip=f.get("clip") or None,
        lora=f.get("lora") or None,
        lora_strength=f.get("lora_strength", 1.0),
    )
    return _run_job("background", prompt or f"{name}: remove background", f.get("job"), f.get("client"),
                    lambda on_progress: comfy_client.background(
                        COMFY_SERVER, name, upload.read(), mode=mode,
                        timeout=int(f.get("timeout", 3600)), on_progress=on_progress, **params))


@app.route("/api/videofx", methods=["POST"])
def videofx():
    """Video effects: multipart form with a `video` file and `effect` = "smooth" (RIFE
    in-between frames, `multiplier` 2-4) or "remove_bg" (subject on a plain `color`:
    green, black, white or blue)."""
    upload = request.files.get("video")
    if not upload or not upload.filename:
        return jsonify(error="A video file is required."), 400
    f = request.form
    effect = f.get("effect", "smooth")
    name = Path(upload.filename).name
    label = f"{name} ×{f.get('multiplier', 2)} smooth" if effect == "smooth" else f"{name}: remove background"
    return _run_job("videofx", label, f.get("job"), f.get("client"), lambda on_progress:
        comfy_client.video_fx(
            COMFY_SERVER, name, upload.read(),
            effect=effect,
            multiplier=f.get("multiplier", 2),
            color=f.get("color", "green"),
            timeout=int(f.get("timeout", 3600)),
            on_progress=on_progress,
        ))


@app.route("/api/upscale", methods=["POST"])
def upscale():
    """Enlarge a photo: multipart form with an `image` file and `scale` (2 or 4)."""
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify(error="An image file is required."), 400
    f = request.form
    scale = f.get("scale", 2)
    quality = "best" if f.get("quality") == "best" else "fast"
    name = Path(upload.filename).name

    return _run_job("upscale", f"{name} ×{scale}", f.get("job"), f.get("client"), lambda on_progress:
        comfy_client.upscale(
            COMFY_SERVER,
            name,
            upload.read(),
            scale=scale,
            model=comfy_client.UPSCALE_MODELS[quality],
            timeout=int(f.get("timeout", 1800)),
            on_progress=on_progress,
        ))


@app.route("/api/enhance", methods=["POST"])
def enhance():
    """Rewrite a short prompt into a detailed one with the local LLM (Ollama)."""
    data = request.get_json(force=True, silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="Type a prompt to enhance first."), 400
    try:
        better = prompt_helper.enhance(prompt, mode=data.get("mode", "generate"))
    except prompt_helper.EnhanceError as exc:
        return jsonify(error=str(exc)), 502
    return jsonify(prompt=better, model=prompt_helper.MODEL)


VIDEO_TYPES = (".mp4", ".webm", ".mkv", ".gif")
INLINE_LIMIT = 4 * 1024 * 1024  # bytes; larger images are returned by URL only


def _save(result):
    """Write rendered images (or videos) to output/ and build the JSON response body.
    Images come back inline as data URIs; videos only by URL (they're big)."""
    images = []
    for name, blob in result["images"]:
        (OUTPUT_DIR / name).write_bytes(blob)
        if name.lower().endswith(VIDEO_TYPES):
            images.append({"filename": name, "url": f"/output/{name}", "data": f"/output/{name}", "video": True})
            continue
        images.append({
            "filename": name,
            "url": f"/output/{name}",
            # big ones (upscales) by URL only, like videos
            "data": (f"/output/{name}" if len(blob) > INLINE_LIMIT else
                     "data:image/png;base64," + base64.b64encode(blob).decode()),
        })

    return dict(prompt_id=result["prompt_id"], seed=result["seed"], images=images)


@app.route("/api/jobs")
def jobs():
    """Jobs sent by one browser (`?client=`), newest first, including finished ones."""
    client = request.args.get("client", "")
    return jsonify(jobs=[_job_view(j) for j in reversed(list(JOBS.values()))
                         if j["client"] == client])


def _job_view(rec):
    p = dict(rec)
    if p.get("state") == "queued" and p.get("prompt_id"):
        try:
            p["ahead"] = comfy_client.jobs_ahead(COMFY_SERVER, p["prompt_id"])
        except Exception:
            pass
    return p


@app.route("/api/jobs/<job>", methods=["DELETE"])
def forget_job(job):
    """Remove a finished job's result from the gallery (`?image=` just one file of a
    batch), so it doesn't come back on reload. The file itself stays in output/."""
    rec = JOBS.get(job)
    if not rec or rec.get("state") not in ("done", "failed", "cancelled"):
        return jsonify(forgotten=False)
    image = request.args.get("image")
    rest = [img for img in rec.get("result", {}).get("images", [])
            if image and img["filename"] != image]
    if rest:
        rec["result"] = dict(rec["result"], images=rest)
    else:
        JOBS.pop(job, None)
    _save_jobs()
    return jsonify(forgotten=True)


@app.route("/api/progress/<job>")
def progress(job):
    return jsonify(_job_view(JOBS.get(job, {"state": "unknown"})))


@app.route("/api/cancel/<job>", methods=["POST"])
def cancel(job):
    """Cancel a job started from this UI: dequeue it or interrupt it if running."""
    prompt_id = JOBS.get(job, {}).get("prompt_id")
    if not prompt_id:
        return jsonify(error="That job isn't queued yet (or already finished)."), 404
    try:
        comfy_client.cancel(COMFY_SERVER, prompt_id)
    except comfy_client.ComfyError as exc:
        return jsonify(error=str(exc)), 502
    return jsonify(cancelled=prompt_id)


# What made a file in output/, from its filename prefix (the SaveImage/SaveVideo prefixes
# in the workflows). Longest prefix first, so "..._edit" wins over the plain t2i one.
OUTPUT_KINDS = [
    ("Wan2.2_i2v_face_test", "Face video (test)"), ("Wan2.2_ti2v", "Video"),
    ("Qwen_image_2.1_gguf_edit", "Edit"), ("Qwen_image_2.1_gguf_inpaint", "Inpaint"),
    ("Qwen_image_2.1_gguf_uncrop", "Uncrop"), ("Qwen_image_2.1_gguf_pose", "Pose"),
    ("Qwen_image_2.1_gguf_background", "Background"), ("Qwen_image_2.1_gguf_relight", "Relight"),
    ("Qwen_image_2.1_gguf", "Qwen-Image"), ("Krea2_turbo_gguf", "Krea 2"),
    ("Chroma1_HD_gguf", "Chroma"), ("SDXL", "SDXL"), ("pose_map", "Pose map"),
    ("upscale", "Upscale"), ("cutout", "Cut out"), ("background_removed", "Video FX"),
    ("smooth", "Smooth"),
]
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp")


def _output_kind(name):
    for prefix, kind in OUTPUT_KINDS:
        if name.startswith(prefix):
            return kind
    return "Other"


@app.route("/api/gallery")
def gallery():
    """Everything in output/ (images and videos), newest first: {"items": [{"filename",
    "url", "video", "kind", "size", "mtime", "prompt"?, "seed"?}], "total"}.
    `?type=image|video`, `?offset=`, `?limit=` (default 60) page through it."""
    want = request.args.get("type", "")
    offset = max(0, int(request.args.get("offset", 0)))
    limit = min(200, max(1, int(request.args.get("limit", 60))))
    # prompt / seed from the job records that produced each file
    known = {}
    for rec in JOBS.values():
        for img in (rec.get("result") or {}).get("images", []):
            known[img["filename"]] = {"prompt": rec.get("prompt"), "seed": rec["result"].get("seed")}
    files = []
    for path in OUTPUT_DIR.rglob("*"):
        name = path.name.lower()
        video = name.endswith(VIDEO_TYPES)
        if not path.is_file() or not (video or name.endswith(IMAGE_TYPES)):
            continue
        if want and want != ("video" if video else "image"):
            continue
        st = path.stat()
        rel = path.relative_to(OUTPUT_DIR).as_posix()
        files.append(dict({"filename": path.name, "url": f"/output/{rel}", "video": video,
                           "kind": _output_kind(path.name), "size": st.st_size, "mtime": st.st_mtime},
                          **known.get(path.name, {})))
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return jsonify(items=files[offset:offset + limit], total=len(files))


@app.route("/output/<path:name>")
def output(name):
    return send_from_directory(OUTPUT_DIR, name)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        # 7870: ports 5000-5999 belong to the DREAM Robotics fleet (RIFT is on 5000)
        port=int(os.environ.get("PORT", 7870)),
        debug=bool(os.environ.get("FLASK_DEBUG")),
    )
