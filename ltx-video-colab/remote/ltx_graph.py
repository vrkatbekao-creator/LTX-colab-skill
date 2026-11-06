# -*- coding: utf-8 -*-
"""ComfyUI API graphs for LTX-2.5, rebuilt by hand from the official templates in Comfy-Org/workflow_templates
(templates/video_ltx2_5_t2v.json, video_ltx2_5_i2v.json, video_ltx2_5_flf2v.json at commit
21d7cc4fb9afd983957f2d2d6b1d583860ccb40b). Same nodes, same sigmas, same strengths; left out: the optional
Gemma prompt-enhancer branch (off by default in the templates) and the UI-only helper nodes (math, primitives,
resolution selector), whose values are computed here instead.

Only core ComfyUI nodes are used: no custom node packs.

  text   : two stages. Half-size latent, 8 distilled steps -> latent x2 upsampler -> 3 refine steps.
  image  : same two stages, the start image written into the latent before each stage (strength 0.7, then 1.0).
  frames : one stage at full size, first and/or last frame added as guides (strength 0.7 each).
"""

MODELS = {
    "unet": "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
    "clip": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
    "vae": "ltx-2.5-video-vae-bf16.safetensors",
    "audio_vae": "ltx-2.5-audio-vae-bf16.safetensors",
    "upscaler": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors",
}
FPS = 24
SIGMAS_STAGE1 = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
SIGMAS_STAGE2 = "0.85, 0.7250, 0.4219, 0.0"
NEGATIVE = "pc game, console game, video game, cartoon, childish, ugly"

SIZES = {  # (resolution, aspect) -> output width, height
    ("480P", "16:9"): (832, 480), ("480P", "9:16"): (480, 832),
    ("720P", "16:9"): (1280, 720), ("720P", "9:16"): (720, 1280),
    ("1080P", "16:9"): (1920, 1088), ("1080P", "9:16"): (1088, 1920),
}


def frame_count(seconds):
    """LTX wants 8k+1 frames; 24 fps means whole seconds land there exactly."""
    return max(1, round(float(seconds) * FPS / 8)) * 8 + 1


def build(mode, prompt, seconds, resolution, aspect, seed, first=None, last=None, negative=None, prefix="ltxskill/out"):
    """mode: text | image | frames. first/last: file names already in ComfyUI's input folder."""
    if (resolution, aspect) not in SIZES:
        raise ValueError(f"unsupported size {resolution} {aspect}")
    if mode == "image" and not first:
        raise ValueError("image mode needs a start image")
    if mode == "frames" and not (first or last):
        raise ValueError("frames mode needs a first or a last frame")
    w, h = SIZES[(resolution, aspect)]
    n = frame_count(seconds)
    g = {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": MODELS["unet"], "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": MODELS["clip"], "type": "ltxv", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["vae"]}},
        "avae": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["audio_vae"]}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["clip", 0]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or NEGATIVE, "clip": ["clip", 0]}},
        "cond": {"class_type": "LTXVConditioning",
                 "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "frame_rate": float(FPS)}},
        "lat_a": {"class_type": "LTXVEmptyLatentAudio",
                  "inputs": {"frames_number": n, "frame_rate": FPS, "batch_size": 1, "audio_vae": ["avae", 0]}},
    }
    if mode in ("text", "image"):
        _two_stage(g, mode, w, h, n, seed, first)
        video, audio = ["dec", 0], ["adec", 0]
    elif mode == "frames":
        _frames(g, w, h, n, seed, first, last)
        video, audio = ["dec", 0], ["adec", 0]
    else:
        raise ValueError(f"unknown mode {mode}")
    g["vid"] = {"class_type": "CreateVideo", "inputs": {"images": video, "audio": audio, "fps": float(FPS)}}
    g["save"] = {"class_type": "SaveVideo",
                 "inputs": {"video": ["vid", 0], "filename_prefix": prefix, "format": "mp4", "format.codec": "auto"}}
    return g


def _image_in(g, key, name, scale):
    g[key] = {"class_type": "LoadImage", "inputs": {"image": name}}
    g[key + "_s"] = scale
    g[key + "_s"]["inputs"]["image"] = [key, 0]
    g[key + "_p"] = {"class_type": "LTXVPreprocess", "inputs": {"image": [key + "_s", 0], "img_compression": 18}}
    return [key + "_p", 0]


def _sampler(g, tag, latent, seed, sigmas, sampler, positive=("cond", 0), negative=("cond", 1)):
    g["noise" + tag] = {"class_type": "RandomNoise", "inputs": {"noise_seed": int(seed)}}
    g["guide" + tag] = {"class_type": "LTXVDualCFGGuider",
                        "inputs": {"model": ["unet", 0], "positive": list(positive), "negative": list(negative),
                                   "video_cfg": 1.0, "audio_cfg": 1.0}}
    g["sampler" + tag] = sampler
    g["sigmas" + tag] = {"class_type": "ManualSigmas", "inputs": {"sigmas": sigmas}}
    g["run" + tag] = {"class_type": "SamplerCustomAdvanced",
                      "inputs": {"noise": ["noise" + tag, 0], "guider": ["guide" + tag, 0],
                                 "sampler": ["sampler" + tag, 0], "sigmas": ["sigmas" + tag, 0],
                                 "latent_image": latent}}


def _two_stage(g, mode, w, h, n, seed, first):
    g["lat_v"] = {"class_type": "EmptyLTXVLatentVideo",
                  "inputs": {"width": w // 2, "height": h // 2, "length": n, "batch_size": 1}}
    video_latent = ["lat_v", 0]
    if mode == "image":
        img = _image_in(g, "img", first, {"class_type": "ImageScaleToMaxDimension",
                                          "inputs": {"upscale_method": "lanczos", "largest_size": 1536}})
        g["i2v1"] = {"class_type": "LTXVImgToVideoInplace",
                     "inputs": {"vae": ["vae", 0], "image": img, "latent": video_latent, "strength": 0.7, "bypass": False}}
        video_latent = ["i2v1", 0]
    g["av1"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": video_latent, "audio_latent": ["lat_a", 0]}}
    _sampler(g, "1", ["av1", 0], seed, SIGMAS_STAGE1, {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}})
    g["sep1"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["run1", 0]}}
    g["ups_model"] = {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": MODELS["upscaler"]}}
    g["ups"] = {"class_type": "LTXVLatentUpsampler",
                "inputs": {"samples": ["sep1", 0], "upscale_model": ["ups_model", 0], "vae": ["vae", 0]}}
    video_latent = ["ups", 0]
    if mode == "image":
        g["i2v2"] = {"class_type": "LTXVImgToVideoInplace",
                     "inputs": {"vae": ["vae", 0], "image": ["img_p", 0], "latent": video_latent, "strength": 1.0, "bypass": False}}
        video_latent = ["i2v2", 0]
    g["av2"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": video_latent, "audio_latent": ["sep1", 1]}}
    # the templates refine with a fixed noise seed of 42
    _sampler(g, "2", ["av2", 0], 42, SIGMAS_STAGE2, {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral"}})
    g["sep2"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["run2", 0]}}
    _decode(g, ["sep2", 0], ["sep2", 1])


def _frames(g, w, h, n, seed, first, last):
    g["lat_v"] = {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": w, "height": h, "length": n, "batch_size": 1}}
    pos, neg, lat = ["cond", 0], ["cond", 1], ["lat_v", 0]
    for key, name, idx in (("first", first, 0), ("last", last, -1)):
        if not name:
            continue
        img = _image_in(g, key, name, {"class_type": "ImageScale",
                                        "inputs": {"upscale_method": "nearest-exact", "width": w, "height": h, "crop": "center"}})
        g["guide_" + key] = {"class_type": "LTXVAddGuide",
                             "inputs": {"positive": pos, "negative": neg, "vae": ["vae", 0], "latent": lat,
                                        "image": img, "frame_idx": idx, "strength": 0.7}}
        pos, neg, lat = ["guide_" + key, 0], ["guide_" + key, 1], ["guide_" + key, 2]
    g["av1"] = {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": lat, "audio_latent": ["lat_a", 0]}}
    _sampler(g, "1", ["av1", 0], seed, SIGMAS_STAGE1,
             {"class_type": "SamplerEulerAncestral", "inputs": {"eta": 0.0, "s_noise": 1.0}}, positive=pos, negative=neg)
    # the template takes the denoised output (slot 1) here
    g["sep1"] = {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["run1", 1]}}
    g["crop"] = {"class_type": "LTXVCropGuides", "inputs": {"positive": pos, "negative": neg, "latent": ["sep1", 0]}}
    _decode(g, ["crop", 2], ["sep1", 1])


def build_tts(prompt, seconds, seed, negative=None, prefix="ltxskill/out"):
    """Text to audio (speech, sound effects, ambience), no picture. Follows Lightricks' official T2A example
    (ComfyUI-LTXVideo example_workflows/2.3/LTX-2.3_T2A_Single_Stage_Distilled.json): one stage, 8 distilled
    steps, euler_ancestral_cfg_pp, CFG 1, with the model switched to audio-only. On LTX-2.5 the distilled
    transformer is used directly, so the 2.3 example's distilled LoRA is not needed.
    Needs Lightricks' ComfyUI-LTXVideo node pack (LTXVAudioOnlyModel, LTXVAudioOnlyEmptyVideoLatent)."""
    n = frame_count(seconds)
    return {
        "unet": {"class_type": "UNETLoader", "inputs": {"unet_name": MODELS["unet"], "weight_dtype": "default"}},
        "audio_only": {"class_type": "LTXVAudioOnlyModel", "inputs": {"model": ["unet", 0]}},
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": MODELS["clip"], "type": "ltxv", "device": "default"}},
        "avae": {"class_type": "VAELoader", "inputs": {"vae_name": MODELS["audio_vae"]}},
        "pos": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["clip", 0]}},
        "neg": {"class_type": "CLIPTextEncode", "inputs": {"text": negative or NEGATIVE, "clip": ["clip", 0]}},
        "cond": {"class_type": "LTXVConditioning",
                 "inputs": {"positive": ["pos", 0], "negative": ["neg", 0], "frame_rate": float(FPS)}},
        "lat_a": {"class_type": "LTXVEmptyLatentAudio",
                  "inputs": {"frames_number": n, "frame_rate": FPS, "batch_size": 1, "audio_vae": ["avae", 0]}},
        "dummy_v": {"class_type": "LTXVAudioOnlyEmptyVideoLatent", "inputs": {}},
        "av": {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": ["dummy_v", 0], "audio_latent": ["lat_a", 0]}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": int(seed)}},
        "guide": {"class_type": "CFGGuider",
                  "inputs": {"model": ["audio_only", 0], "positive": ["cond", 0], "negative": ["cond", 1], "cfg": 1.0}},
        "sampler": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral_cfg_pp"}},
        "sigmas": {"class_type": "ManualSigmas", "inputs": {"sigmas": SIGMAS_STAGE1}},
        "run": {"class_type": "SamplerCustomAdvanced",
                "inputs": {"noise": ["noise", 0], "guider": ["guide", 0], "sampler": ["sampler", 0],
                           "sigmas": ["sigmas", 0], "latent_image": ["av", 0]}},
        "sep": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["run", 0]}},
        "adec": {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["sep", 1], "audio_vae": ["avae", 0]}},
        "save": {"class_type": "SaveAudio", "inputs": {"audio": ["adec", 0], "filename_prefix": prefix}},
    }


def _decode(g, video_latent, audio_latent):
    g["dec"] = {"class_type": "VAEDecodeTiled",
                "inputs": {"samples": video_latent, "vae": ["vae", 0], "tile_size": 512, "overlap": 64,
                           "temporal_size": 64, "temporal_overlap": 16}}
    g["adec"] = {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": audio_latent, "audio_vae": ["avae", 0]}}
