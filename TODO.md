# TODO

## Image editing ("photo in → edited photo out")

Let a user upload a photo and give an instruction like *"change the dress to a red
evening gown"* — keeping the rest of the image intact. The current app is
**text-to-image only**; this adds an edit mode alongside it.

- [ ] **Model:** download a **Qwen-Image-Edit** GGUF (the editing sibling of the base
      model), ~4–8 GB, Q4 to fit the 6 GB 2060. Put it in `models/diffusion_models/`.
- [ ] **Workflow:** add a ComfyUI edit graph (`workflows/qwen_image_2.1_gguf_edit_api.json`)
      — image loader → encode → sampler with the edit model → decode → save.
- [ ] **API:** add an edit endpoint to `app.py` (e.g. `POST /api/edit`) that accepts an
      uploaded image + instruction, queues the edit workflow via `comfy_client.py`, and
      returns the result. Extend `comfy_client.py` to upload the input image to ComfyUI
      (`/upload/image`) and reference it in the graph.
- [ ] **UI:** add an **Edit** tab to the web UI (`templates/` + `static/`) with a
      photo-upload control and an instruction box, next to the existing **Generate** tab.

## Inpainting (masked editing)

Paint a mask over a region (e.g. the dress) and regenerate only that area, leaving the
rest of the photo untouched. Best control for "keep me, change the outfit", and it uses
the **base Q4_K_M model already downloaded** — no extra model needed.

- [ ] **Workflow:** add an inpaint graph (`workflows/qwen_image_2.1_gguf_inpaint_api.json`)
      — `LoadImage` + mask → `VAEEncodeForInpaint` → `KSampler` → `VAEDecode` → `SaveImage`.
- [ ] **API:** `POST /api/inpaint` accepting image + mask (PNG alpha) + prompt; upload both
      to ComfyUI via `comfy_client.py` and wire them into the graph.
- [ ] **UI:** brush/canvas to paint the mask over the uploaded photo (the bulk of the work),
      plus a prompt box. Share the Edit tab.

## LoRA support (optional)

Stack a LoRA adapter on the base model for style/behavior tweaks.

- [ ] Add a GGUF-compatible `LoraLoader` node between `UnetLoaderGGUF` and the sampler in
      the workflow, plus an optional `lora` field in the API/UI to pick one from
      `models/loras/`.

### Notes
- The repo's `qwen-image-2.1-uncensored-lora.safetensors` (30 MB) is **redundant** with the
  UC GGUFs (uncensoring is already baked in). It mainly matters if you switch to a stock
  (censored) Qwen-Image base — then this LoRA re-applies the effect.
- Plain img2img with the *base* model can restyle a whole photo but is unreliable for
  targeted edits (it changes everything) — inpainting or the Edit model is the right tool
  for "keep me, change the outfit".
- **Inpainting** = precise, mask-based, uses the base model. **Qwen-Image-Edit** = no mask,
  instruction-driven, needs the separate Edit model. Consider doing inpainting first (no
  extra download).
- Do all of this **after** the base text-to-image path is confirmed working end-to-end.
