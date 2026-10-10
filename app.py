"""Flask server for Qwen-Image 2.1 GGUF.

A web UI and JSON API over the ComfyUI text-to-image workflow in this repo.
ComfyUI must be running separately (see the README); this server talks to it
over HTTP, so point COMFY_SERVER at it if it is not on the default port.

    python app.py                 # http://127.0.0.1:5000
    COMFY_SERVER=http://host:8188 python app.py
"""
import base64
import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import comfy_client

BASE = Path(__file__).parent
OUTPUT_DIR = BASE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

with (BASE / "config.json").open(encoding="utf-8") as fh:
    CONFIG = json.load(fh)["Config"]

COMFY_SERVER = os.environ.get("COMFY_SERVER", "http://127.0.0.1:8188").rstrip("/")

# Quantizations published alongside the model, offered in the UI dropdown.
UNETS = [
    "qwen-image-2.1-UC-Q4_K_M.gguf",
    "qwen-image-2.1-UC-Q4_0.gguf",
    "qwen-image-2.1-UC-Q5_K_M.gguf",
    "qwen-image-2.1-UC-Q6_K.gguf",
    "qwen-image-2.1-UC-Q8_0.gguf",
    "qwen-image-2.1-UC-BF16.gguf",
]
CLIPS = [
    "qwen3vl_8b_int8_convrot.safetensors",
    "qwen3vl_8b_bf16.safetensors",
]

app = Flask(__name__)


@app.route("/")
def index():
    return render_template(
        "index.html",
        config=CONFIG,
        server=COMFY_SERVER,
        unets=UNETS,
        clips=CLIPS,
    )


@app.route("/api/health")
def health():
    up = comfy_client.ping(COMFY_SERVER)
    return jsonify(comfy="up" if up else "down", server=COMFY_SERVER), (200 if up else 503)


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True, silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="A prompt is required."), 400

    try:
        result = comfy_client.generate(
            COMFY_SERVER,
            prompt=prompt,
            negative=(data.get("negative") or "").strip(),
            width=data.get("width", 1024),
            height=data.get("height", 1024),
            steps=data.get("steps", 25),
            cfg=data.get("cfg", 1.0),
            seed=data.get("seed"),
            batch=data.get("batch", 1),
            unet=data.get("unet") or None,
            clip=data.get("clip") or None,
            timeout=int(data.get("timeout", 600)),
        )
    except comfy_client.ComfyError as exc:
        return jsonify(error=str(exc)), 502
    except (ValueError, TypeError) as exc:
        return jsonify(error=f"Bad parameter: {exc}"), 400

    images = []
    for name, blob in result["images"]:
        (OUTPUT_DIR / name).write_bytes(blob)
        images.append({
            "filename": name,
            "url": f"/output/{name}",
            "data": "data:image/png;base64," + base64.b64encode(blob).decode(),
        })

    return jsonify(prompt_id=result["prompt_id"], seed=result["seed"], images=images)


@app.route("/output/<path:name>")
def output(name):
    return send_from_directory(OUTPUT_DIR, name)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=bool(os.environ.get("FLASK_DEBUG")),
    )
