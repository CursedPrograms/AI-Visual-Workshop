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
