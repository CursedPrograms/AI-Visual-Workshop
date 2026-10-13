"""Every model the Workshop knows, for the Models page: where each file comes from,
how big it is, and the ComfyUI folder it goes in.

"base" models are the Workshop's standard set; the rest are optional extras you can
download from the Models page. A model marked "test" is being tried out.
Downloads go to this repo's models/<folder>/ (MODELS_DIR), which ComfyUI already
reads through extra_model_paths.yaml, so a new file shows up without a restart.
"""

HF = "https://huggingface.co"


def hf(repo, path, folder, size):
    return {"url": f"{HF}/{repo}/resolve/main/{path}", "name": path.rsplit("/", 1)[-1],
            "folder": folder, "size": size, "repo": repo}


CATALOG = [
    # ---- image ----
    {"id": "qwen", "name": "Qwen-Image 2.1 (uncensored)", "kind": "Image", "base": True,
     "license": "Qwen Research License",
     "note": "The main model: Generate, Edit, Inpaint, Uncrop and Pose.",
     "files": [
         hf("abenzerps/Qwen-Image-2.1-Uncensored-GGUF", "qwen-image-2.1-UC-Q4_K_M.gguf", "diffusion_models", 4604558112),
         hf("abenzerps/Qwen-Image-2.1-Uncensored-GGUF", "text_encoders/qwen3vl_8b_int8_convrot.safetensors", "text_encoders", 9350798360),
         hf("abenzerps/Qwen-Image-2.1-Uncensored-GGUF", "vae/qwen_image_2.1_vae_bf16.safetensors", "vae", 675509688),
     ]},
    {"id": "krea2", "name": "Krea 2 Turbo", "kind": "Image", "base": True,
     "license": "Krea 2 Community License",
     "note": "Fast text-to-image in 8 steps.",
     "files": [
         hf("molbal/krea2-gguf", "krea2_turbo_bf16-Q4_0.gguf", "diffusion_models", 8314016800),
         hf("Comfy-Org/Krea-2", "text_encoders/qwen3vl_4b_fp8_scaled.safetensors", "text_encoders", 5242467968),
         hf("Comfy-Org/Krea-2", "vae/qwen_image_vae.safetensors", "vae", 253806246),
     ]},
    {"id": "realvis", "name": "RealVisXL V5 Lightning (SDXL)", "kind": "Image", "base": True,
     "license": "OpenRAIL++",
     "note": "Photoreal SDXL, uncensored training, 6 steps: a few seconds per image.",
     "files": [
         hf("SG161222/RealVisXL_V5.0_Lightning", "RealVisXL_V5.0_Lightning_fp16.safetensors", "checkpoints", 6938065512),
     ]},
    {"id": "chroma", "name": "Chroma1-HD", "kind": "Image", "base": False,
     "license": "Apache 2.0",
     "note": "Uncensored 8.9B model (Flux-based), strong on photos and art. ~26 steps.",
     "files": [
         hf("silveroxides/Chroma1-HD-GGUF", "Chroma1-HD-Q4_K_M.gguf", "diffusion_models", 5566533792),
         hf("comfyanonymous/flux_text_encoders", "t5xxl_fp8_e4m3fn_scaled.safetensors", "text_encoders", 5157348688),
         hf("Comfy-Org/Lumina_Image_2.0_Repackaged", "split_files/vae/ae.safetensors", "vae", 335304388),
     ]},
    {"id": "noobai", "name": "NoobAI-XL 1.1 (SDXL)", "kind": "Image", "base": False,
     "license": "Fair AI Public License",
     "note": "Anime / illustration SDXL, uncensored. ~25 steps, CFG 5.",
     "files": [
         hf("Laxhar/noobai-XL-1.1", "NoobAI-XL-v1.1.safetensors", "checkpoints", 7105349958),
     ]},
    {"id": "juggernaut", "name": "Juggernaut XI (SDXL)", "kind": "Image", "base": False,
     "license": "CC BY-NC-ND 4.0 (non-commercial)",
     "note": "Cinematic photoreal SDXL all-rounder. ~25 steps, CFG 5.",
     "files": [
         hf("RunDiffusion/Juggernaut-XI-v11", "Juggernaut-XI-byRunDiffusion.safetensors", "checkpoints", 7105350536),
     ]},
    {"id": "dmd2", "name": "DMD2 4-step LoRA (SDXL)", "kind": "LoRA", "base": False,
     "license": "CC BY-NC 4.0 (non-commercial)",
     "note": "Makes any SDXL checkpoint run in 4 steps at CFG 1 (pick it under LoRA).",
     "files": [
         hf("tianweiy/DMD2", "dmd2_sdxl_4step_lora_fp16.safetensors", "loras", 393854592),
     ]},
    # ---- video ----
    {"id": "wan", "name": "Wan 2.2 TI2V-5B", "kind": "Video", "base": True,
     "license": "Apache 2.0",
     "note": "Video from a prompt or a photo, 24 fps.",
     "files": [
         hf("QuantStack/Wan2.2-TI2V-5B-GGUF", "Wan2.2-TI2V-5B-Q5_K_M.gguf", "diffusion_models", 3810603360),
         hf("city96/umt5-xxl-encoder-gguf", "umt5-xxl-encoder-Q5_K_M.gguf", "text_encoders", 4145878880),
         hf("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/vae/wan2.2_vae.safetensors", "vae", 1409400960),
     ]},
    {"id": "wanface", "name": "Wan 2.2 I2V-A14B, faces (test)", "kind": "Video", "base": True, "test": True,
     "license": "Apache 2.0",
     "note": "(test) Photo to video, much better faces and identity. LightX2V 4-step, 16 fps. "
             "Shares the Wan text encoder.",
     "files": [
         hf("jayn7/WAN2.2-I2V_A14B-DISTILL-LIGHTX2V-4STEP-GGUF",
            "high_noise_260412/wan2.2_i2v_A14b_high_noise_lightx2v_4step_720p_260412-Q3_K_M.gguf",
            "diffusion_models", 7185947264),
         hf("jayn7/WAN2.2-I2V_A14B-DISTILL-LIGHTX2V-4STEP-GGUF",
            "low_noise_260412/wan2.2_i2v_A14b_low_noise_lightx2v_4step_720p_260412-Q3_K_M.gguf",
            "diffusion_models", 7185947264),
         hf("Comfy-Org/Wan_2.2_ComfyUI_Repackaged", "split_files/vae/wan_2.1_vae.safetensors", "vae", 253815318),
     ]},
    # ---- tools ----
    {"id": "sdpose", "name": "SDPose whole-body", "kind": "Tool", "base": True,
     "license": "MIT",
     "note": "Finds body, hand and face keypoints for the Pose tool.",
     "files": [
         hf("Comfy-Org/SDPose", "checkpoints/sdpose_wholebody_fp16.safetensors", "checkpoints", 1916645792),
     ]},
    {"id": "birefnet", "name": "BiRefNet background removal", "kind": "Tool", "base": True,
     "license": "MIT",
     "note": "Finds the subject for the Background tool and Video FX (remove background).",
     "files": [
         hf("Comfy-Org/BiRefNet", "background_removal/birefnet.safetensors", "background_removal", 444473596),
     ]},
    {"id": "rife", "name": "RIFE v4.26 frame interpolation", "kind": "Tool", "base": True,
     "license": "MIT / Apache 2.0",
     "note": "Smooth video: adds in-between frames (Video FX, and the smooth link under videos).",
     "files": [
         hf("Comfy-Org/frame_interpolation", "frame_interpolation/rife_v4.26.safetensors", "frame_interpolation", 22674688),
     ]},
    {"id": "ultrasharp", "name": "4x-UltraSharp V2", "kind": "Tool", "base": True,
     "license": "CC BY-NC-SA 4.0 (non-commercial)",
     "note": "The Upscale tool's model.",
     "files": [
         hf("Kim2091/UltraSharpV2", "4x-UltraSharpV2.safetensors", "upscale_models", 139792588),
     ]},
]

BY_ID = {m["id"]: m for m in CATALOG}

# ComfyUI loader inputs that list each folder's files (to see what ComfyUI already has,
# wherever extra_model_paths.yaml points).
LOADERS = {
    "diffusion_models": [("UnetLoaderGGUF", "unet_name")],
    "text_encoders": [("CLIPLoader", "clip_name"), ("CLIPLoaderGGUF", "clip_name")],
    "vae": [("VAELoader", "vae_name")],
    "checkpoints": [("CheckpointLoaderSimple", "ckpt_name")],
    "upscale_models": [("UpscaleModelLoader", "model_name")],
    "loras": [("LoraLoaderModelOnly", "lora_name")],
    "background_removal": [("LoadBackgroundRemovalModel", "bg_removal_name")],
    "frame_interpolation": [("FrameInterpolationModelLoader", "model_name")],
}
