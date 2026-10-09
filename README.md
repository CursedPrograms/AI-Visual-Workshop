# Qwen-Image 2.1 GGUF: ComfyUI Workflow

A text-to-image ComfyUI workflow for the GGUF quantizations of Qwen-Image 2.1 from
[abenzerps/Qwen-Image-2.1-Uncensored-GGUF](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF).

| File | Purpose |
| --- | --- |
| `workflows/qwen_image_2.1_gguf_t2i.json` | Drag into the ComfyUI UI |
| `workflows/qwen_image_2.1_gguf_t2i_api.json` | API-format graph for scripting |
| `generate.py` | Queues the API workflow on a running ComfyUI server |

## 1. Install ComfyUI-GGUF

Use the leejet fork. It supports Qwen-Image 2.1 natively.

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/leejet/ComfyUI-GGUF
```

If you have the older `city96/ComfyUI-GGUF` and get `Unknown model architecture!`, switch to the fork.

## 2. Download the models

```text
ComfyUI/models/
├── diffusion_models/qwen-image-2.1-UC-Q4_K_M.gguf       # or Q4_0 / Q5_K_M / Q6_K / Q8_0 / BF16
├── text_encoders/qwen3vl_8b_int8_convrot.safetensors    # or qwen3vl_8b_bf16.safetensors
└── vae/qwen_image_2.1_vae_bf16.safetensors
```

With `huggingface-cli`:

```bash
REPO=abenzerps/Qwen-Image-2.1-Uncensored-GGUF
huggingface-cli download $REPO qwen-image-2.1-UC-Q4_K_M.gguf --local-dir ComfyUI/models/diffusion_models
huggingface-cli download $REPO text_encoders/qwen3vl_8b_int8_convrot.safetensors --local-dir ComfyUI/models
huggingface-cli download $REPO vae/qwen_image_2.1_vae_bf16.safetensors --local-dir ComfyUI/models
```

Q4_K_M uses about 4.6 GB of VRAM. The int8 text encoder uses about 9.4 GB and can run in system RAM.
If you run out of VRAM, start ComfyUI with `--lowvram`.

## 3. Run

**In the UI:** drag `workflows/qwen_image_2.1_gguf_t2i.json` onto the canvas.
Check the file names in the three loader nodes, type a prompt and click Queue.

**From a script** (ComfyUI must be running):

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

## License

The model weights are under the Qwen Research License. The workflow and scripts are under the [LICENSE](LICENSE) in this repo.
