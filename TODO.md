# TODO

## Image editing ("photo in → edited photo out")

Let a user upload a photo and give an instruction like *"change the dress to a red
evening gown"* — keeping the rest of the image intact. The current app is
**text-to-image only**; this adds an edit mode alongside it.

- [x] **Model:** no extra download — Qwen-Image 2.1 edits natively. `TextEncodeQwenImage21`
      takes the photo as a reference image (plus the VAE) and outputs a matching latent.
- [x] **Workflow:** `workflows/qwen_image_2.1_gguf_edit_api.json` — `LoadImage` →
      `TextEncodeQwenImage21` (image + VAE) → `KSampler` on its latent → decode → save.
- [x] **API:** `POST /api/edit` (multipart: `image` file + `prompt`, optional `resolution`,
      `steps`, `cfg`, `seed`, …). `comfy_client.py` uploads the photo via `/upload/image`.
- [x] **UI:** **Generate / Edit photo** toggle with photo upload, preview and instruction box.

## Inpainting (masked editing)

Paint a mask over a region (e.g. the dress) and regenerate only that area, leaving the
rest of the photo untouched. Best control for "keep me, change the outfit", and it uses
the **base Q4_K_M model already downloaded** — no extra model needed.

- [x] **Workflow:** `workflows/qwen_image_2.1_gguf_inpaint_api.json` — photo as reference
      image in `TextEncodeQwenImage21`, `VAEEncode` → `SetLatentNoiseMask` → `KSampler` →
      `VAEDecode` → `ImageCompositeMasked` back onto the original (unmasked pixels untouched).
- [x] **API:** `POST /api/inpaint` (multipart: `image` + `mask` files at the same size, multiples
      of 32, white = regenerate; plus `prompt`, optional `denoise`, `steps`, `cfg`, `seed`, …).
- [x] **UI:** **Inpaint** tab — brush/erase/clear over the photo on a canvas; the browser sizes
      photo and mask to ~resolution² and feathers the mask edge.

## Uncrop (outpainting)

- [x] **Uncrop** tab: aspect presets / zoom-out / per-side % sliders with a live preview; the
      browser pads the photo with grey and builds a feathered border mask (4 % feathered overlap into the
      photo), then reuses `POST /api/inpaint` with the unpadded photo as `reference` (`kind=uncrop` for the filename prefix).
- [x] ✨ Enhance has an `uncrop` mode that describes the surroundings, not the subject.

## LoRA support

Stack a LoRA adapter on the model for style/behavior tweaks.

- [x] `LoraLoaderModelOnly` inserted between `UnetLoaderGGUF` and the sampler when a LoRA is
      picked (all three graphs); `lora` / `lora_strength` in the API, LoRA + Strength in the UI
      (list from `GET /api/loras`, i.e. whatever ComfyUI sees). `models/loras/` added to
      `extra_model_paths`.
- [x] Tested with the repo's `qwen-image-2.1-uncensored-lora.safetensors` (strength 0.8, no unloaded-key warnings).

## Krea 2 as a second model (optional)

Krea 2 Turbo (12B DiT, June 2026) as an alternative text-to-image model, 8 steps at cfg 1.

- [~] **License:** Krea 2 Community License — the PDF on krea/Krea-2-Turbo needs an HF login,
      so it hasn't been read here; guides summarise it as free below a revenue/seat threshold.
      Read it before any commercial use.
- [x] **Files:** `krea2_turbo_bf16-Q4_0.gguf` (8.31 GB, molbal/krea2-gguf — tagged `krea2`;
      vantagewithai's are tagged `qwen_image`), `qwen3vl_4b_fp8_scaled.safetensors` (5.24 GB) and
      `qwen_image_vae.safetensors` (0.25 GB) from Comfy-Org/Krea-2. Stored in `F:/AIModels/krea2`
      (C: had only 15 GB free), wired in via a `krea2:` entry in `extra_model_paths.yaml`.
- [x] **Loader node:** none needed — the leejet ComfyUI-GGUF fork already lists `krea2`, and
      ComfyUI core supports the model and `CLIPLoader` type `krea2`.
- [x] **Workflow + API/UI:** `workflows/krea2_turbo_gguf_t2i_api.json` (from Comfy-Org's Krea 2
      Turbo template), `model: "krea2"` in `/api/generate`, **Model** picker on the Generate tab.
- [x] **Verified** on the RTX 2060: 1024×1024, 8 steps in 401 s including the first model load
      from the F: hard disk (~3.6 GB on the GPU, the rest offloaded to RAM).
- [ ] `generate.py` CLI is still Qwen-only.

### Notes
- The repo's `qwen-image-2.1-uncensored-lora.safetensors` (30 MB) is **redundant** with the
  UC GGUFs (uncensoring is already baked in). It mainly matters if you switch to a stock
  (censored) Qwen-Image base — then this LoRA re-applies the effect.
- Plain img2img with the *base* model can restyle a whole photo but is unreliable for
  targeted edits (it changes everything) — inpainting or the Edit model is the right tool
  for "keep me, change the outfit".
- **Inpainting** = precise, mask-based. **Edit** (done) = no mask, instruction-driven; both
  use the base model.
- Do all of this **after** the base text-to-image path is confirmed working end-to-end.

## Pose and Upscale

- [x] **Pose:** `workflows/qwen_image_2.1_gguf_pose_api.json` — ComfyUI core `SDPoseKeypointExtractor`
      → `SDPoseDrawKeypoints` (skeleton saved as `pose_map_*`) → `TextEncodeQwenImage21` with the
      skeleton as reference image 1. `POST /api/pose`, **Pose** tool. No ControlNet download.
- [x] **Upscale:** `workflows/upscale_api.json` — `4x-UltraSharpV2` then `ImageScaleBy` for 2×.
      `POST /api/upscale`, **Upscale** tool and an **upscale** link on every image result.
- [ ] Pose: optional second photo for *who* (keep the person from photo B, pose from photo A).
- [ ] Depth / edges control (same reference-image approach, or a Qwen-Image ControlNet).

## Models page and extra models

- [x] **Models page** (Studio / Models switch in the header): every model with installed / partly
      downloaded / missing status, size and license; **Download** / **Resume** / **Cancel** run in
      the server (`model_manager.py`, catalog in `model_catalog.py`), resumable, into `models/`.
- [x] Model dropdowns mark models whose files ComfyUI doesn't have as *(not installed)*.
- [ ] **Download (base):** RealVisXL V5 Lightning (6.9 GB) — paused, not started.
- [x] **Download (base, test):** Wan 2.2 I2V-A14B faces (test) — 14.4 GB, SHA-256 verified.
- [x] **Face model (test) first run** (2026-10-13): demo portrait, 480×832, 49 frames, 6 min on the RTX 2060; identity held through a smile, hair tuck and head tilt. Keep the (test) mark until a few more portraits.
- [ ] **Download (base):** SDPose (Pose tool) — paused at ~18 %.
- [x] **SDXL** family in Generate (`workflows/sdxl_t2i_api.json`): any SDXL checkpoint, per-file
      steps/CFG presets (Lightning 6 steps / CFG 1.5; others 25 / 5).
- [x] **Chroma1-HD** (optional, Apache 2.0, uncensored, Flux-based 8.9B): `workflows/chroma1_hd_gguf_t2i_api.json`,
      GGUF Q4_K_M 5.6 GB + T5 + Flux VAE. Not downloaded.
- [x] **Face video model (test):** Wan 2.2 I2V-A14B LightX2V 4-step (`workflows/wan2.2_i2v_a14b_face_test_gguf_api.json`),
      **Video model** picker on the Video tool, needs a start photo, 16 fps. Not run yet (files not downloaded).
- [ ] Optional models listed but not downloaded: Chroma1-HD, NoobAI-XL 1.1, Juggernaut XI, DMD2 LoRA.
- [ ] Test each new model once its files are in; then drop the (test) mark from the face model if it holds up.

## Background, Relight, Video FX (local versions of the Bria cloud nodes)

- [x] **Background** tool: remove (BiRefNet → transparent PNG) / replace (BiRefNet mask → Qwen-Image
      inpaints the background). **cut out** link on image results. Not run yet: BiRefNet (444 MB) not downloaded.
- [x] **Relight** tool: `/api/edit` with `kind=relight`, the prompt wrapped to change only the light.
- [x] **Video FX** tool: RIFE smoothing (2–4×, **smooth** link on video results) and per-frame
      background removal onto a solid colour. Not run yet: RIFE (23 MB) / BiRefNet not downloaded.
- [x] Bria nodes left out on purpose: they upload to Bria's cloud, cost Comfy.org credits and filter content.
- [x] BiRefNet + RIFE downloaded. [ ] Restart ComfyUI once so it sees the new folders, then test.
- [x] Model pickers show an info card on hover (best for, speed, license, installed).

## Next tools

- [ ] **Restyle** (img2img: photo → oil painting, anime, …)
- [ ] **Gallery** of everything in `output/`
- [ ] **Depth / edges** control

## UI

- [x] Tool dropdown instead of a tab row; collapsible sections; hideable panel; lightbox;
      drag-and-drop photos; header link to the GitHub Pages site.

## Queue and jobs

- [x] **Model reloading in the queue:** within Qwen (t2i/edit/inpaint/LoRA) nothing is re-read
      from disk; each job only swaps text encoder → UNet → VAE onto the 6 GB GPU (normal). The
      real reload was **switching Qwen ↔ Krea 2**: ComfyUI's default RAM-pressure cache evicts
      every model the current job doesn't use (inactive threshold = all RAM), costing ~154 s per
      switch back to Krea on the F: disk. Fix: start ComfyUI with `--cache-ram 6 16` (README).
      Verified: Qwen/Krea alternating, each loaded from disk once, then 17–27 s per job.
- [x] **Timeout:** live once Flask restarted (queue time doesn't count, only running time).
- [x] **Jobs that survive closing the window:** jobs are tracked on the server (`JOBS` in
      `app.py`, tagged with a per-browser `client` id from localStorage); `GET /api/jobs` lets
      the page rebuild its gallery and resume progress on reopen.
- [ ] **Project name:** decide at the end.
