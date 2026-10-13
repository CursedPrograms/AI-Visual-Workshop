# AI Visual Workshop — vision

**One local repo. One web app. Every visual-AI task in one place — no googling, no
tool-hopping.** A single front end (this Flask app) drives one ComfyUI backend, with a
tab for each capability. Local, offline, uncensored, on your own GPU.

```
          ┌─────────────────────  AI Visual Workshop (Flask UI + API)  ─────────────────────┐
browser ─▶│  Generate │ Edit │ Inpaint │ Outpaint │ Upscale │ Restyle │ Video │ Models      │
          └──────────────────────────────────┬────────────────────────────────────────────┘
                                              │ HTTP (comfy_client)
                                   ┌──────────▼──────────┐
                                   │       ComfyUI        │  ← one backend, many workflows
                                   │  Qwen-Image / WAN /  │
                                   │  LTX / upscalers …   │
                                   └──────────────────────┘
```

## Principle

- **Uncensored only.** Every module uses the uncensored ("UC") / abliterated model builds —
  no censored or safety-filtered variants anywhere in the workshop. New capabilities
  (edit, video, etc.) must ship with an uncensored model or they don't ship.
- **One app, tabbed.** Each tab = one task = one ComfyUI workflow JSON + one API endpoint.
- **Shared plumbing.** `comfy_client.py` (queue → poll → fetch) is reused by every module;
  adding a capability means adding a workflow + endpoint + tab, nothing more.
- **One model store.** `models/` holds everything; a Models tab downloads/switches them.
- **One gallery.** All outputs (images + video) land in `output/` with a browsable history.
- **Runs on the LAN** as `http://qwen.flask:7870` so any device (or the robots) can use it.

## Modules

| # | Module | Engine | Status |
|---|---|---|---|
| 1 | **Generate** (text-to-image) | Qwen-Image 2.1 GGUF | ✅ Built |
| 2 | **Edit** (instruction: "change the dress") | Qwen-Image-Edit | 📋 TODO |
| 3 | **Inpaint** (mask a region, regenerate it) | base model | 📋 TODO |
| 4 | **Outpaint / expand** (extend the canvas) | base model | ⬜ Planned |
| 5 | **Restyle / img2img** | base model | ⬜ Planned |
| 6 | **Upscale** (2× / 4×) | 4x-UltraSharp V2 | ✅ Built |
| 7 | **Background** remove / replace | segmentation + inpaint | ⬜ Planned |
| 8 | **Control: pose** (depth / edges later) | SDPose + Qwen-Image reference | ✅ Pose built |
| 9 | **Video** (text-to-video, image-to-video) | Wan 2.2 TI2V-5B; I2V-A14B faces (test) | ✅ Built |
| 10 | **LoRA** stacking | any | 📋 TODO |
| 11 | **Models** manager (download, switch quant/encoder/LoRA) | — | ✅ Built (Models page) |
| 12 | **Gallery / history** (browse, re-run, delete outputs) | — | ⬜ Planned |

(Per-module build steps live in `TODO.md`.)

## Hardware notes (RTX 2060, 6 GB VRAM / 64 GB RAM)

- Images (Qwen GGUF Q4–Q8) and inpaint/edit: comfortable with `--lowvram`.
- Video: start with **LTX-Video** or **WAN 2.x GGUF i2v** (short clips); heavy models
  (Hunyuan, Mochi) are rented-GPU territory.
- Everything loads through the one ComfyUI you already have — new capabilities are mostly
  "download a model + drop in a workflow".

## Open decisions

- **Repo identity:** decided 2026-10-13: *this* repo became the Workshop, renamed from
  `Qwen-Image-2.1-Uncensored-GGUF` to `AI-Visual-Workshop`. Qwen-Image is module #1, and
  Video (Wan 2.2 TI2V-5B) is module #2.
- **Relation to the ecosystem:** the Workshop is the visual service DREAM/Friday call for
  "dreaming" (see that project), announced on the LAN as `qwen.flask`.
