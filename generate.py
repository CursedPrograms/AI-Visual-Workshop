"""Queue a Qwen-Image 2.1 GGUF text-to-image job on a running ComfyUI server."""
import argparse
import json
import random
import urllib.request
from pathlib import Path

WORKFLOW = Path(__file__).parent / "workflows" / "qwen_image_2.1_gguf_t2i_api.json"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prompt")
    p.add_argument("--server", default="http://127.0.0.1:8188")
    p.add_argument("--unet", help="GGUF file in models/diffusion_models (default: Q4_K_M)")
    p.add_argument("--clip", help="text encoder file in models/text_encoders")
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--height", type=int, default=1024)
    p.add_argument("--steps", type=int, default=25)
    p.add_argument("--cfg", type=float, default=1.0)
    p.add_argument("--negative", default="", help="only has an effect when --cfg > 1")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--prefix", default="Qwen_image_2.1_gguf")
    a = p.parse_args()

    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    if a.unet:
        wf["1"]["inputs"]["unet_name"] = a.unet
    if a.clip:
        wf["2"]["inputs"]["clip_name"] = a.clip
    wf["4"]["inputs"]["prompt"] = a.prompt
    wf["4"]["inputs"]["negative_prompt"] = a.negative
    wf["5"]["inputs"].update(width=a.width, height=a.height, batch_size=a.batch)
    wf["6"]["inputs"].update(
        seed=a.seed if a.seed is not None else random.randint(0, 2**53),
        steps=a.steps,
        cfg=a.cfg,
    )
    wf["8"]["inputs"]["filename_prefix"] = a.prefix

    req = urllib.request.Request(
        f"{a.server}/prompt",
        data=json.dumps({"prompt": wf}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        res = json.load(r)
    print(f"Queued {res['prompt_id']} (seed {wf['6']['inputs']['seed']}); "
          f"images land in ComfyUI/output/{a.prefix}_*.png")


if __name__ == "__main__":
    main()
