"""Make a Wan 2.2 video from the command line, through a running ComfyUI server.

    python generate_video.py "she turns toward the camera and smiles" --image photo.png
    python generate_video.py "waves crashing on a rocky shore at sunset"       # text-to-video
    python generate_video.py "..." --image x.png --width 1280 --height 704 --frames 121 --steps 30

The video is saved to output/ (and ComfyUI's own output/video/).
"""
import argparse
import sys
import time
from pathlib import Path

import comfy_client

OUTPUT_DIR = Path(__file__).parent / "output"


def main():
    p = argparse.ArgumentParser(description="Wan 2.2 TI2V-5B video through ComfyUI")
    p.add_argument("prompt", help="what happens: the motion, the camera, the scene")
    p.add_argument("--image", help="start photo (omit for text-to-video)")
    p.add_argument("--server", default="http://127.0.0.1:8188")
    p.add_argument("--width", type=int, default=832, help="multiple of 32 (native: 1280)")
    p.add_argument("--height", type=int, default=480, help="multiple of 32 (native: 704)")
    p.add_argument("--frames", type=int, default=49, help="4n+1: 49 = 2 s, 121 = 5 s at 24 fps")
    p.add_argument("--fps", type=float, default=24.0)
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--cfg", type=float, default=5.0)
    p.add_argument("--shift", type=float, default=8.0)
    p.add_argument("--negative", default="")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--unet", help="Wan GGUF file (default: Wan2.2-TI2V-5B-Q5_K_M.gguf)")
    p.add_argument("--clip", help="text encoder (default: umt5-xxl-encoder-Q5_K_M.gguf)")
    a = p.parse_args()

    if not comfy_client.ping(a.server):
        sys.exit(f"ComfyUI isn't running at {a.server}: start it first (see the README).")
    image = Path(a.image) if a.image else None
    progress = lambda e: e.get("max") and print(f"\r  step {e['value']}/{e['max']}", end="", flush=True)
    print(("image-to-video from " + image.name if image else "text-to-video") +
          f", {a.width}x{a.height}, {a.frames} frames, {a.steps} steps")
    start = time.time()
    try:
        result = comfy_client.video(
            a.server, image.name if image else None, image.read_bytes() if image else None,
            prompt=a.prompt, negative=a.negative, width=a.width, height=a.height, frames=a.frames,
            fps=a.fps, steps=a.steps, cfg=a.cfg, shift=a.shift, seed=a.seed, unet=a.unet, clip=a.clip,
            on_progress=progress)
    except (comfy_client.ComfyError, ValueError) as e:
        sys.exit(f"\n{e}")
    OUTPUT_DIR.mkdir(exist_ok=True)
    for name, blob in result["images"]:
        (OUTPUT_DIR / name).write_bytes(blob)
        print(f"\nDone in {time.time() - start:.0f}s (seed {result['seed']}) -> output/{name}")


if __name__ == "__main__":
    main()
