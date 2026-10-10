[![Twitter: @NorowaretaGemu](https://img.shields.io/badge/X-@NorowaretaGemu-blue.svg?style=flat)](https://x.com/NorowaretaGemu)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<div align="center">
  <a href="https://ko-fi.com/cursedentertainment">
    <img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="ko-fi" style="width: 20%;"/>
  </a>
</div>

<div align="center">
  <img alt="Python" src="https://img.shields.io/badge/python%20-%23323330.svg?&style=for-the-badge&logo=python&logoColor=white"/>
  <img alt="Flask" src="https://img.shields.io/badge/flask%20-%23323330.svg?&style=for-the-badge&logo=flask&logoColor=white"/>
</div>

---

# Qwen-Image 2.1 GGUF

A **Flask server** — web UI and JSON API — for text-to-image generation with the GGUF
quantizations of Qwen-Image 2.1, plus the ComfyUI workflow it runs on. The model comes from
[abenzerps/Qwen-Image-2.1-Uncensored-GGUF](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF).

## 📖 Overview

<details>
<summary><b>Overview</b></summary>

The Flask app in `app.py` serves a browser UI and a small JSON API. It does not run the model
itself — it drives a **ComfyUI** backend over HTTP, patching the API-format workflow in this repo
with your prompt and settings, waiting for the render, then returning the images to the browser
and saving them under `output/`.

| File | Purpose |
| --- | --- |
| `app.py` | Flask web server (UI + API) |
| `comfy_client.py` | Queues the workflow on ComfyUI and fetches results |
| `generate.py` | One-shot CLI that queues a job (no server needed) |
| `templates/index.html` | The web UI markup |
| `static/style.css`, `static/app.js` | The UI's styles and client logic |
| `run.bat` / `run.ps1` / `run.sh` | Create the venv and start the server on localhost |
| `run-lan.bat` | Start the server on the whole LAN (`0.0.0.0`) |
| `extra_model_paths.example.yaml` | Template to point ComfyUI at this repo's `models/` |
| `workflows/qwen_image_2.1_gguf_t2i.json` | Drag into the ComfyUI UI |
| `workflows/qwen_image_2.1_gguf_t2i_api.json` | API-format graph the server/CLI drive |

</details>

## Architecture

```text
browser ──HTTP──▶ Flask (app.py) ──HTTP──▶ ComfyUI ──▶ Qwen-Image 2.1 GGUF
   ▲                   │                      │
   └── images ◀────────┴── output/*.png ◀─────┘
```

The Flask server is a thin client. **ComfyUI must be running** with the Qwen-Image 2.1 GGUF
models installed (steps 1–2 below). Then start the server (step 3).

## 1. Install ComfyUI-GGUF

Use the leejet fork. It supports Qwen-Image 2.1 natively.

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/leejet/ComfyUI-GGUF
```

If you have the older `city96/ComfyUI-GGUF` and get `Unknown model architecture!`, switch to the fork.

## 2. Download the models

Keep the weights in this repo's `models/` folder (the layout mirrors ComfyUI's):

```text
models/
├── diffusion_models/qwen-image-2.1-UC-Q4_K_M.gguf       # or Q4_0 / Q5_K_M / Q6_K / Q8_0 / BF16
├── text_encoders/qwen3vl_8b_int8_convrot.safetensors    # or qwen3vl_8b_bf16.safetensors
└── vae/qwen_image_2.1_vae_bf16.safetensors
```

With the Hugging Face CLI (`pip install huggingface_hub`; the command is `hf`):

```bash
REPO=abenzerps/Qwen-Image-2.1-Uncensored-GGUF
hf download $REPO qwen-image-2.1-UC-Q4_K_M.gguf --local-dir models/diffusion_models
hf download $REPO text_encoders/qwen3vl_8b_int8_convrot.safetensors --local-dir models
hf download $REPO vae/qwen_image_2.1_vae_bf16.safetensors --local-dir models
```

The default set is about **14.6 GB** (4.6 + 9.35 + 0.68). Q4_K_M uses about 4.6 GB of VRAM;
the int8 text encoder is ~9.4 GB and can sit in system RAM. If you run out of VRAM, start
ComfyUI with `--lowvram` (recommended for 6–8 GB cards).

### Check the downloads

A download that was interrupted and resumed can end up the right size but full of zeros, and
ComfyUI loads it without complaint (see [Troubleshooting](#troubleshooting)). Compare SHA-256
hashes before you run anything:

| File | SHA-256 |
| --- | --- |
| `qwen-image-2.1-UC-Q4_K_M.gguf` | `e79c8a009f2ecbdb6c70fd663d9aea9ee304a0d91f347e4169a756b8ad141b41` |
| `qwen3vl_8b_int8_convrot.safetensors` | `8bfd0f6e12abf2d2d697ecc888e5e90b0d6741d6708f05799f53afa560452e8f` |
| `qwen_image_2.1_vae_bf16.safetensors` | `bb21f7473051e1ac368515dd3f2e15cd44d7a11748ee8823e1ddca3e4876b7c9` |

```bash
# Windows (PowerShell)
Get-FileHash models\text_encoders\qwen3vl_8b_int8_convrot.safetensors
# macOS / Linux / Git Bash
sha256sum models/text_encoders/qwen3vl_8b_int8_convrot.safetensors
```

If a hash doesn't match, delete the file and its entry under `models/.cache/huggingface` and
download it again. `pip install hf_xet` makes Hugging Face downloads faster and more reliable.

### Point ComfyUI at these models

Rather than copying 14 GB into ComfyUI's own folder, copy `extra_model_paths.example.yaml`
from this repo to `extra_model_paths.yaml` in the ComfyUI root (edit `base_path` to match)
so ComfyUI reads the weights in place:

```yaml
qwen_image_gguf:
    base_path: C:/cc/Qwen-Image-2.1-Uncensored-GGUF/models
    diffusion_models: diffusion_models
    unet: diffusion_models
    text_encoders: text_encoders
    clip: text_encoders
    vae: vae
```

### Start ComfyUI

On a 6 GB card (tested on an RTX 2060), these flags cut render time from about 10 s to 4 s
per step:

```bash
cd ComfyUI
python main.py --disable-comfy-compiler --disable-dynamic-vram --disable-async-offload
```

Add `--output-directory <this repo>/output` if you want images you make in ComfyUI's own UI to
land in this repo too. Images made through the Flask server are always saved to `output/`.

## 3. Run the Flask server

```bash
# Windows
run.bat
# PowerShell
./run.ps1
# macOS / Linux
./run.sh
```

Each script creates a `venv`, installs `requirements.txt` and launches the server at
**http://127.0.0.1:5000**. Open it, confirm the status dot reads *ComfyUI connected*, type a
prompt and click **Generate**. To run it by hand:

```bash
pip install -r requirements.txt
python app.py
```

To expose it on the whole local network instead of just this machine, use **`run-lan.bat`**
(binds `0.0.0.0:5000`), or set `HOST=0.0.0.0` by hand.

### Serve it as `http://qwen.flask:5000`

Give the server a friendly name on your LAN. Map `qwen.flask` to the host's IP — per device in
its hosts file:

```text
192.168.0.101   qwen.flask
```

or network-wide with a local DNS entry (dnsmasq / Pi-hole: `address=/qwen.flask/192.168.0.101`).
Open **port 5000** in the host's firewall so other devices can reach it. Then browse to
`http://qwen.flask:5000` (use `http://`, and skip the `www.`).

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `COMFY_SERVER` | `http://127.0.0.1:8188` | Where ComfyUI is listening |
| `HOST` | `127.0.0.1` | Interface Flask binds (`0.0.0.0` to expose on the LAN) |
| `PORT` | `5000` | Port Flask binds |
| `FLASK_DEBUG` | *(off)* | Any non-empty value enables Flask debug mode |

```bash
COMFY_SERVER=http://192.168.1.50:8188 python app.py
```

## Run on a separate machine (Raspberry Pi, LAN)

The server is a thin HTTP client, so the web UI and the GPU work can live on different
machines. A low-power box (e.g. a **Raspberry Pi 5**) can host the UI around the clock while
a GPU PC does the generation:

```text
Raspberry Pi 5 (Flask UI, always on)  ──HTTP──▶  GPU PC (ComfyUI + Qwen-Image 2.1)
```

On the **GPU PC**, start ComfyUI so it accepts LAN connections:

```bash
python main.py --listen --lowvram        # --listen binds 0.0.0.0:8188
```

On the **Pi** only Flask and its tiny dependencies are needed — no torch, no models:

```bash
pip install -r requirements.txt
HOST=0.0.0.0 COMFY_SERVER=http://<gpu-pc-ip>:8188 python app.py
```

Then browse to `http://<pi-ip>:5000`. The Pi cannot generate on its own — a 20B model needs
the GPU PC — it just serves the page and relays requests.

## API

**`POST /api/generate`** — JSON in, JSON out.

```bash
curl -X POST http://127.0.0.1:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "a watercolour lighthouse at dusk", "width": 1344, "height": 768, "steps": 30}'
```

| Field | Default | Notes |
| --- | --- | --- |
| `prompt` | *(required)* | Text prompt |
| `negative` | `""` | Only used when `cfg > 1` |
| `width` / `height` | `1024` | Multiples of 32, up to 2048 |
| `steps` | `25` | Official pipeline uses 40–50 |
| `cfg` | `1.0` | 1 is the official setting |
| `seed` | random | Integer for reproducibility |
| `batch` | `1` | Images per request |
| `unet` | Q4_K_M | GGUF file in `models/diffusion_models` |
| `clip` | int8 | Text encoder in `models/text_encoders` |

Response: `{ "prompt_id", "seed", "images": [{ "filename", "url", "data" }] }` where `data` is a
base64 PNG and `url` serves the saved file from `output/`.

**`GET /api/health`** — `{"comfy": "up"|"down", "server": "..."}`; HTTP 503 when ComfyUI is down.

## CLI (no server)

`generate.py` queues a single job straight on ComfyUI:

```bash
python generate.py "a watercolour lighthouse on a rocky coast at dusk" --width 1344 --height 768
python generate.py "..." --unet qwen-image-2.1-UC-Q8_0.gguf --steps 40 --seed 42
```

## Settings

- **cfg 1** is the official setting. The negative prompt is ignored unless cfg is above 1.
- **Steps:** the official pipeline uses 40–50 euler steps. The default here is 25, which is faster.
- **Resolution:** native up to 2048×2048. Use multiples of 32.

## Pipeline

`UnetLoaderGGUF` → `KSampler` (euler / simple) → `VAEDecode` → `SaveImage`.
Conditioning comes from `CLIPLoader` (type `qwen_image`) → `TextEncodeQwenImage21`.
The graph follows the official Comfy-Org Qwen-Image 2.1 template, except that it loads
the model with the GGUF loader and leaves out the optional prompt-rewriter LLM.

## Troubleshooting

**Every image is the same flat grey texture, whatever the prompt.** The text encoder file is
damaged. Its embedding table is partly zero-filled, so the model gets no prompt and denoises
pure noise. This happens when a download is interrupted and later "resumed" from a full-size
but incomplete file. Check the hashes in [Check the downloads](#check-the-downloads) and
re-download any file that doesn't match.

**"Cannot reach ComfyUI"** from the API or the red status dot in the UI: ComfyUI isn't running,
or `COMFY_SERVER` points at the wrong host or port.

**`OSError: [WinError 1455] The paging file is too small`** when ComfyUI starts: Windows ran
out of virtual memory while loading PyTorch. Close other heavy programs or enlarge the page
file, then start ComfyUI again.

## License

The model weights are under the Qwen Research License. The workflow and scripts are under the [LICENSE](LICENSE) in this repo.
