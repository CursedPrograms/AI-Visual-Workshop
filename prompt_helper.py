"""Prompt enhancer: rewrites a short prompt into a detailed one with a local
LLM served by Ollama (https://ollama.com). Standard library only.

    OLLAMA_SERVER   default http://127.0.0.1:11434
    OLLAMA_MODEL    default gemma3:4b-it-qat (use a non-reasoning model: a
                    "thinking" model spends its time and output on reasoning)
    OLLAMA_NUM_GPU  default 0 (run on CPU so it never competes with ComfyUI
                    for VRAM); set to e.g. 99 to put all layers on the GPU
"""
import json
import os
import re
import urllib.error
import urllib.request

SERVER = os.environ.get("OLLAMA_SERVER", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:4b-it-qat")
NUM_GPU = int(os.environ.get("OLLAMA_NUM_GPU", 0))

_COMMON = (
    " Keep every detail the user gave and do not contradict it. Reply with the "
    "rewritten prompt only: no preamble, no quotes, no lists, no markdown."
)
SYSTEM = {
    "generate": (
        "You write prompts for a text-to-image model. Expand the user's idea into "
        "one vivid paragraph of 60-120 words: subject, setting, composition and "
        "camera angle, lighting, colours, mood, and medium or photographic style."
        + _COMMON
    ),
    "edit": (
        "You write instructions for an image-editing model that changes a photo the "
        "user supplies. Rewrite the user's request as one or two clear, specific "
        "sentences saying exactly what to change (colour, material, style, details), "
        "then add a short sentence saying everything else stays the same (face, pose, "
        "lighting, background). Under 60 words." + _COMMON
    ),
    "inpaint": (
        "You write prompts for an inpainting model that fills a masked region of a "
        "photo. Describe only what should appear inside that region, in 20-50 words: "
        "object, material, colour, texture, and lighting that matches a photograph. "
        "Do not describe the rest of the image." + _COMMON
    ),
    "uncrop": (
        "You write prompts for an outpainting model that extends a photo beyond its "
        "original borders. From the user's hint, describe in 25-60 words what the wider "
        "surroundings look like: environment, ground, sky or walls, background objects, "
        "and lighting consistent with a photograph. Do not describe the main subject."
        + _COMMON
    ),
    "video": (
        "You write prompts for a text-to-video and image-to-video model. Expand the user's "
        "idea into 40-90 words describing what happens over a few seconds: the subject's "
        "motion and expression, how the camera moves (slow push-in, pan, static), the "
        "setting, lighting and mood. Describe motion as a continuous action, one scene, "
        "no cuts." + _COMMON
    ),
}


class EnhanceError(RuntimeError):
    """Raised when Ollama is unreachable or returns nothing usable."""


def enhance(prompt, mode="generate", timeout=300):
    """Return a richer version of `prompt` for the given UI mode."""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM.get(mode, SYSTEM["generate"])},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"num_gpu": NUM_GPU, "temperature": 0.7, "num_predict": 220},
    }
    req = urllib.request.Request(
        f"{SERVER}/api/chat", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = json.load(r)["message"]["content"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise EnhanceError(f"Ollama error ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise EnhanceError(f"Cannot reach Ollama at {SERVER}: {e.reason}") from e
    except TimeoutError as e:
        raise EnhanceError(f"Ollama took longer than {timeout}s") from e

    # Drop any reasoning a thinking model put in the reply (sometimes without the opening tag).
    text = re.sub(r"^.*</think>", "", text, flags=re.S).strip().strip('"').strip()
    if not text:
        raise EnhanceError("The model returned an empty prompt.")
    return text
