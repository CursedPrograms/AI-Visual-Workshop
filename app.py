"""Flask server for AI Visual Workshop.

A web UI and JSON API over the ComfyUI text-to-image, image-edit, inpaint and
video workflows in this repo.
ComfyUI must be running separately (see the README); this server talks to it
over HTTP, so point COMFY_SERVER at it if it is not on the default port.

    python app.py                 # http://127.0.0.1:5000
    COMFY_SERVER=http://host:8188 python app.py
"""
import base64
import json
import os
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import comfy_client
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
}

# Video: Wan 2.2 TI2V-5B (text-to-video, or image-to-video from a start photo).
VIDEO = {
    "label": "Wan 2.2 TI2V-5B",
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
}
VIDEO_NEGATIVE = (
    "blurry, low quality, worst quality, jpeg artifacts, static, frozen frame, overexposed, "
    "deformed, distorted face, extra fingers, malformed hands, bad anatomy, watermark, text, subtitles"
)

app = Flask(__name__)

# Every job submitted with a `job` id, by id: kind, prompt, the browser that sent it
# (`client`), "state" (starting/queued/running/done/failed/cancelled), step progress and
# the result or error. Kept on the server so a page reopened later can pick its jobs up.
JOBS = {}
MAX_JOBS = 200


def _run_job(kind, prompt, job, client, call):
    """Run call(on_progress) for one job, record how it ends under JOBS[job]
    and turn it into the endpoint's response."""
    rec = None
    if job:
        while len(JOBS) >= MAX_JOBS:  # drop the oldest
            JOBS.pop(next(iter(JOBS)))
        rec = JOBS[job] = {"id": job, "client": client or "", "kind": kind,
                           "prompt": prompt, "created": time.time(), "state": "starting"}
    end = rec.update if rec else lambda **_: None
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
    return render_template(
        "index.html",
        config=CONFIG,
        server=COMFY_SERVER,
        models=MODELS,
        families=dict(MODELS, wan=VIDEO),
        video_negative=VIDEO_NEGATIVE,
    )


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

    return _run_job("edit", prompt, f.get("job"), f.get("client"), lambda on_progress:
        comfy_client.edit(
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
    `width`/`height` are multiples of 32, `frames` is 4n+1 (49 = 2 s at 24 fps)."""
    prompt = (request.form.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="Describe the video first."), 400
    upload = request.files.get("image")
    f = request.form

    return _run_job("video", prompt, f.get("job"), f.get("client"), lambda on_progress:
        comfy_client.video(
            COMFY_SERVER,
            Path(upload.filename).name if upload and upload.filename else None,
            upload.read() if upload and upload.filename else None,
            prompt=prompt,
            negative=(f.get("negative") or "").strip() or VIDEO_NEGATIVE,
            width=f.get("width", 832),
            height=f.get("height", 480),
            frames=f.get("frames", 49),
            fps=f.get("fps", 24),
            steps=f.get("steps", VIDEO["steps"]),
            cfg=f.get("cfg", VIDEO["cfg"]),
            seed=f.get("seed") or None,
            unet=f.get("unet") or None,
            clip=f.get("clip") or None,
            lora=f.get("lora") or None,
            lora_strength=f.get("lora_strength", 1.0),
            timeout=int(f.get("timeout", 7200)),
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
            "data": "data:image/png;base64," + base64.b64encode(blob).decode(),
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


@app.route("/output/<path:name>")
def output(name):
    return send_from_directory(OUTPUT_DIR, name)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=bool(os.environ.get("FLASK_DEBUG")),
    )
