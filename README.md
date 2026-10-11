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

A **Flask server** — web UI and JSON API — for text-to-image generation, instruction-based
photo editing, masked inpainting and uncropping with the GGUF quantizations of Qwen-Image 2.1
(plus optional Krea 2 Turbo for text-to-image), and the ComfyUI workflows it runs on. The model comes from
[abenzerps/Qwen-Image-2.1-Uncensored-GGUF](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF).

- **Generate** — text to image with Qwen-Image 2.1, or **Krea 2 Turbo** (optional, 8 steps).
- **Edit photo** — upload a photo and describe the change (*"make the dress red"*); the base
  model edits natively, no separate edit model needed.
- **Inpaint** — paint a mask over part of a photo and regenerate only that area; everything
  outside the mask is kept pixel for pixel.
- **Uncrop** — extend a photo beyond its borders (to 16:9, 1:1, "zoom out 2×", or per side);
  the model invents the surroundings and the original pixels are kept exactly.
- **✨ Enhance** — rewrite a short prompt into a detailed one with a local LLM (Ollama, optional).
- **LoRA** — stack a style/behaviour LoRA on any mode, with a strength slider.
- **Job queue** — press the button as often as you like; each job gets a card with its queue
  position, a live progress bar and its own **Cancel**. **use as photo** keeps editing a result.

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
| `comfy_client.py` | Uploads photos, queues workflows on ComfyUI, relays progress, cancels and fetches results |
| `prompt_helper.py` | ✨ Enhance: prompt rewriting via a local Ollama model |
| `generate.py` | One-shot CLI that queues a job (no server needed) |
| `templates/index.html` | The web UI markup |
| `static/style.css`, `static/app.js` | The UI's styles and client logic |
| `run.bat` / `run.ps1` / `run.sh` | Create the venv and start the server on localhost |
| `run-lan.bat` | Start the server on the whole LAN (`0.0.0.0`) |
| `extra_model_paths.example.yaml` | Template to point ComfyUI at this repo's `models/` |
| `workflows/qwen_image_2.1_gguf_t2i.json` | Drag into the ComfyUI UI |
| `workflows/qwen_image_2.1_gguf_t2i_api.json` | API-format text-to-image graph the server/CLI drive |
| `workflows/qwen_image_2.1_gguf_edit_api.json` | API-format photo-edit graph |
| `workflows/qwen_image_2.1_gguf_inpaint_api.json` | API-format masked-inpaint graph |
| `workflows/krea2_turbo_gguf_t2i_api.json` | API-format Krea 2 Turbo text-to-image graph (optional) |

</details>

## Architecture

```text
browser ──HTTP──▶ Flask (app.py) ──HTTP + websocket──▶ ComfyUI ──▶ Qwen-Image 2.1 GGUF
   ▲                   │  │                                │
   └── images ◀────────┘  └──HTTP──▶ Ollama (✨ Enhance, optional)
                       output/*.png ◀──────────────────────┘
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
    loras: loras
```

LoRA files go in `models/loras/` (or ComfyUI's own `models/loras/`). ComfyUI reads
`extra_model_paths.yaml` only at startup, so restart it after editing the file.

### Krea 2 Turbo (optional)

A second text-to-image model: [Krea 2](https://huggingface.co/krea/Krea-2-Turbo) Turbo, a 12B
distilled DiT that renders in **8 steps at CFG 1**. It is text-to-image only (Edit and Inpaint
always use Qwen-Image 2.1). Its license is the **Krea 2 Community License** (free below a revenue
/ seat threshold — read it on the model page, which needs a Hugging Face login, before any
commercial use).

| File | Size | From | Folder |
| --- | --- | --- | --- |
| `krea2_turbo_bf16-Q4_0.gguf` | 8.31 GB | [molbal/krea2-gguf](https://huggingface.co/molbal/krea2-gguf) | `diffusion_models/` |
| `qwen3vl_4b_fp8_scaled.safetensors` | 5.24 GB | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2) | `text_encoders/` |
| `qwen_image_vae.safetensors` | 0.25 GB | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2) | `vae/` |

```bash
KREA=F:/AIModels/krea2          # any drive with ~14 GB free
hf download Comfy-Org/Krea-2 vae/qwen_image_vae.safetensors     text_encoders/qwen3vl_4b_fp8_scaled.safetensors --local-dir $KREA
hf download molbal/krea2-gguf krea2_turbo_bf16-Q4_0.gguf --local-dir $KREA/diffusion_models
```

Then add the `krea2:` entry from `extra_model_paths.example.yaml` (with `base_path` set to that
folder) and restart ComfyUI. The leejet ComfyUI-GGUF fork already knows the `krea2`
architecture. Use molbal's files: some other Krea 2 GGUFs are tagged `qwen_image` and may not
load. Krea 2 needs about 8.3 GB for Q4_0, so on a 6 GB card part of it is offloaded to RAM; it is
still quick because it only takes 8 steps. Style LoRAs made for Krea 2 are in
[Comfy-Org/Krea-2/loras](https://huggingface.co/Comfy-Org/Krea-2/tree/main/loras) (each has a
trigger phrase listed in ComfyUI's Krea 2 template).

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

### Using the web UI

The four tabs at the top of the form switch mode:

- **Generate** — prompt, size, steps, CFG, batch, seed. **Model** switches between Qwen-Image 2.1
  and Krea 2 Turbo (steps jump to 8 and the negative prompt is hidden, since Turbo runs at CFG 1).
- **Edit photo** — choose a photo, then type an instruction such as *"change the dress to a red
  evening gown"*. **Resolution** sets the output size (about resolution² pixels); the photo's
  aspect ratio is kept.
- **Inpaint** — choose a photo and paint over the area to change (brush size slider, **Erase**,
  **Clear**). The prompt describes only what goes *inside* the painted area. **Denoise** below 1
  keeps more of the original's shape and colour. Press **Inpaint** again to re-roll with a new
  seed (leave Seed blank); the mask stays.

- **Uncrop** — choose a photo, then pick **Expand to** (1:1, 4:3, 16:9, 9:16, zoom out 1.5×/2×,
  …) or drag the **Left / Right / Top / Bottom** sliders (extra canvas as % of the photo). The
  preview shows the grey area that will be generated. The prompt is optional — describe the
  wider scene (*"a sunlit beach with a boardwalk"*) to steer it. **Resolution** is the size of
  the whole expanded image. Large expansions work best in steps: uncrop a little, **use as
  photo**, uncrop again.

Every result has **use as photo**, which makes it the new working photo (from Generate it
switches to Edit) so you can keep refining; **← Previous photo** steps back. That history lives
in the browser tab — all results are also saved in `output/`.

**Queueing:** the Generate / Edit / Inpaint / Uncrop button never locks — every press queues a new
job, and ComfyUI runs them one after another. Each job gets a card at the top of the gallery
showing its prompt, *Queued — 2 jobs ahead → Loading models → step n/25 — %* with a progress bar,
and its own **Cancel**, which removes it from the ComfyUI queue or interrupts it mid-render
(other jobs are not touched). The card turns into the result when it finishes; earlier results
stay below, newest first. Settings are captured when you press the button, so you can change the
prompt, photo or mask for the next job right away. (Browsers allow about 6 connections per site,
so keep it to 4–5 queued jobs per tab.) Waiting in the queue never times out; the time limit (30 min for
Generate, 60 min for Edit / Inpaint / Uncrop, or the `timeout` API field in seconds) only starts
when the job actually runs, and a job that runs past it is stopped.

**Models & LoRA** (collapsed, under Seed) picks the GGUF quantization and text encoder for the
current model, and a **LoRA** with its **Strength**. The LoRA list is whatever ComfyUI can see;
use a LoRA trained for the model you're running (a Krea 2 LoRA won't do anything useful on
Qwen-Image, and vice versa).

**✨ Enhance** next to the prompt rewrites it with the local LLM for the current tab (a rich scene
for Generate, a precise instruction for Edit, the masked area's contents for Inpaint); **Undo**
restores what you typed.

### ✨ Enhance setup (optional)

Install [Ollama](https://ollama.com) and pull a small model:

```bash
ollama pull gemma3:4b-it-qat
```

It runs on the **CPU by default** (`OLLAMA_NUM_GPU=0`) so it never takes VRAM from ComfyUI. A
rewrite takes about 6–20 s once the model is loaded (the first call after a while loads it, ~1
minute); while ComfyUI is rendering, the two share the CPU and it is slower. Avoid "thinking"
models such as `qwen3:4b` — they spend the time and output on reasoning instead of the prompt.
Without Ollama everything else works — the button just reports that it can't reach it.

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
| `OLLAMA_SERVER` | `http://127.0.0.1:11434` | Where Ollama is listening (✨ Enhance) |
| `OLLAMA_MODEL` | `gemma3:4b-it-qat` | Model used to rewrite prompts (prefer a non-"thinking" model) |
| `OLLAMA_NUM_GPU` | `0` | Layers on the GPU (`0` = CPU only; e.g. `99` = all on GPU) |

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
| `model` | `qwen` | `qwen` (Qwen-Image 2.1) or `krea2` (Krea 2 Turbo) |
| `negative` | `""` | Only used when `cfg > 1` |
| `width` / `height` | `1024` | Multiples of 32, up to 2048 |
| `steps` | `25` (`8` for krea2) | Official Qwen pipeline uses 40–50; Krea 2 Turbo uses 8 |
| `cfg` | `1.0` | 1 is the official setting |
| `seed` | random | Integer for reproducibility |
| `batch` | `1` | Images per request |
| `unet` | Q4_K_M | GGUF file in `models/diffusion_models` |
| `clip` | int8 | Text encoder in `models/text_encoders` |
| `lora` | *(none)* | LoRA filename as listed by `/api/loras` |
| `lora_strength` | `1.0` | LoRA weight (negative values invert it) |
| `job` | *(none)* | Any id you choose, to poll progress or cancel (see below) |
| `timeout` | `1800` (`3600` for edit / inpaint) | Max seconds of *running* time; queue waiting doesn't count |

Response: `{ "prompt_id", "seed", "images": [{ "filename", "url", "data" }] }` where `data` is a
base64 PNG and `url` serves the saved file from `output/`.

**`POST /api/edit`** — multipart form: `image` (file) + `prompt` (the edit instruction), plus
optional `resolution` (default 1024), `negative`, `steps`, `cfg`, `seed`, `unet`, `clip`, `lora`,
`lora_strength`, `job`.

```bash
curl -X POST http://127.0.0.1:5000/api/edit \
  -F image=@photo.png -F "prompt=change the dress to a red evening gown" -F seed=42
```

**`POST /api/inpaint`** — multipart form: `image` and `mask` files **of the same size, in
multiples of 32** (white = regenerate, black = keep; the red channel is read), `prompt` for the
masked area, plus optional `denoise` (default 1.0), `negative`, `steps`, `cfg`, `seed`, `unet`,
`clip`, `lora`, `lora_strength`, `job`.

```bash
curl -X POST http://127.0.0.1:5000/api/inpaint \
  -F image=@photo_960x1088.png -F mask=@mask_960x1088.png -F "prompt=a blue sequined dress"
```

Both return the same shape as `/api/generate`. Uncrop is `/api/inpaint` with a padded image (the
photo on a larger grey canvas) and a mask that is white over the new border; send `kind=uncrop`
to save results as `Qwen_image_2.1_gguf_uncrop_*.png`.

**`POST /api/enhance`** — `{"prompt": "...", "mode": "generate"|"edit"|"inpaint"}` →
`{"prompt": "<rewritten>", "model": "gemma3:4b-it-qat"}`; HTTP 502 if Ollama is unreachable.

**`GET /api/progress/<job>`** — `{"state": "starting"|"queued"|"running", "value", "max",
"prompt_id", "ahead"}` for a request sent with that `job` id (`value`/`max` are sampler steps;
`ahead` is how many ComfyUI jobs run before it while it's queued).

**`POST /api/cancel/<job>`** — dequeue or interrupt that job; the original request then returns
HTTP 409 `{"error": "Cancelled.", "cancelled": true}`.

**`GET /api/loras`** — `{"loras": ["file.safetensors", ...]}`: every LoRA ComfyUI can see.

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
- **Edit / inpaint are slower** than text-to-image: the reference photo roughly doubles the
  sequence the model attends over. On an RTX 2060 (6 GB) expect about 24 s per step, so 25
  steps ≈ 10 minutes, versus about 4 s per step for plain generation.

## Pipeline

**Text-to-image:** `UnetLoaderGGUF` → `KSampler` (euler / simple) → `VAEDecode` → `SaveImage`.
Conditioning comes from `CLIPLoader` (type `qwen_image`) → `TextEncodeQwenImage21`.
The graph follows the official Comfy-Org Qwen-Image 2.1 template, except that it loads
the model with the GGUF loader and leaves out the optional prompt-rewriter LLM.

**Edit:** `LoadImage` feeds `TextEncodeQwenImage21` as reference image 1 (with the VAE), so the
Qwen3-VL encoder sees the photo and its VAE latents are spliced into the sequence. The node's
`latent` output (an empty latent at the photo's size) goes to `KSampler`.

**Krea 2 Turbo:** `UnetLoaderGGUF` → `KSampler` (8 steps, cfg 1, euler / simple) → `VAEDecode` →
`SaveImage`, with `CLIPLoader` (type `krea2`) → `CLIPTextEncode` for the prompt and
`ConditioningZeroOut` as the negative, following Comfy-Org's Krea 2 Turbo template.

**LoRA (any graph):** when a LoRA is chosen, `LoraLoaderModelOnly` is inserted between the model
loader and `KSampler`.

**Uncrop:** the browser places the photo on a larger mid-grey canvas (multiples of 32, about
resolution² pixels) and builds a mask that is white over the border and reaches 4 % into the
photo, feathered, so the seam is regenerated and blended. That pair runs through the Inpaint
graph below, with a default "extend the photo outward…" instruction plus your optional scene
text — and the **unpadded photo is sent as the reference image** (`reference` field): shown the
grey canvas, the model just reproduces the grey border instead of filling it.

**Inpaint:** as Edit, with the photo also `VAEEncode`d and masked by `SetLatentNoiseMask`
(mask from `LoadImageMask`), so only the masked area is resampled. `ImageCompositeMasked` then
pastes the decoded result back onto the original through the mask. The browser scales photo
and mask to the same multiple-of-32 size and feathers the mask edge before upload.

## Troubleshooting

**Every image is the same flat grey texture, whatever the prompt.** The text encoder file is
damaged. Its embedding table is partly zero-filled, so the model gets no prompt and denoises
pure noise. This happens when a download is interrupted and later "resumed" from a full-size
but incomplete file. Check the hashes in [Check the downloads](#check-the-downloads) and
re-download any file that doesn't match.

**"Cannot reach ComfyUI"** from the API or the red status dot in the UI: ComfyUI isn't running,
or `COMFY_SERVER` points at the wrong host or port.

**✨ Enhance says "Cannot reach Ollama"** — Ollama isn't running (start the Ollama app or
`ollama serve`), or `OLLAMA_SERVER` is wrong. **It takes minutes** — ComfyUI is rendering and
both are fighting over the CPU; wait for the render, or set `OLLAMA_NUM_GPU=99` if you have
spare VRAM.

**No progress bar, just a spinner** — the `websocket-client` package is missing from the Flask
venv; run `pip install -r requirements.txt`. Generation still works without it.

**`OSError: [WinError 1455] The paging file is too small`** when ComfyUI starts: Windows ran
out of virtual memory while loading PyTorch. Close other heavy programs or enlarge the page
file, then start ComfyUI again.

## License

The model weights are under the Qwen Research License. The workflow and scripts are under the [LICENSE](LICENSE) in this repo.
