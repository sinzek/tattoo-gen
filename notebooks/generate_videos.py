"""Run one CUDA text-to-video checkpoint against CSV prompts and save MP4/JSON pairs."""

import argparse
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import time


# Each profile specifies the model, repository, height, width, frame count, FPS, steps and guidance.
PROFILES = {
    "ltx2-bf16": ("LTX-2", "Lightricks/LTX-2", 512, 768, 121, 24, 30, 3.0),
    "ltx2-distilled": ("LTX-2", "rootonchair/LTX-2-19b-distilled", 512, 768, 121, 24, 8, 1.0),
    "mochi-bf16": ("Mochi 1", "genmo/mochi-1-preview", 480, 848, 121, 30, 28, 4.5),
    "mochi-int8": ("Mochi 1", "genmo/mochi-1-preview", 480, 848, 121, 30, 28, 4.5),
    "cosmos3-bf16": ("Cosmos3 Nano", "nvidia/Cosmos3-Nano", 480, 848, 121, 24, 28, 6.0),
    "cosmos3-fp8": ("Cosmos3 Nano", "nvidia/Cosmos3-Nano-FP8", 480, 848, 121, 24, 28, 6.0),
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--revision", help="Checkpoint revision or SHA. The resolved SHA is recorded.")
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--prompt-set", choices=("dataset", "model_selection"), required=True)
    parser.add_argument("--prompt-id", type=int, nargs="+", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--method", choices=("baseline", "proposed"), default="baseline")
    parser.add_argument("--run-label", default="run", help="Use pilot for the small review cohort.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--height", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--frames", type=int)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--guidance", type=float)
    parser.add_argument("--negative-prompt")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,23}", args.run_label):
        parser.error("run-label must be 1–24 lowercase letters, numbers, dashes or underscores.")
    if not 0 <= args.seed < 2**63 or any(pid <= 0 for pid in args.prompt_id):
        parser.error("Use positive prompt IDs and a nonnegative SQLite-sized seed.")
    return args


def load_pipeline(profile, repo, revision, torch, token):
    from diffusers import DiffusionPipeline

    kwargs = {"revision": revision, "token": token, "dtype": torch.bfloat16}
    if profile == "mochi-int8":
        from diffusers import BitsAndBytesConfig, MochiTransformer3DModel
        from transformers import BitsAndBytesConfig as TextQuantization, T5EncoderModel

        kwargs.update(dtype=torch.float16, device_map="balanced")
        kwargs["text_encoder"] = T5EncoderModel.from_pretrained(
            repo, revision=revision, token=token, subfolder="text_encoder",
            dtype=torch.float16, quantization_config=TextQuantization(load_in_8bit=True),
        )
        kwargs["transformer"] = MochiTransformer3DModel.from_pretrained(
            repo, revision=revision, token=token, subfolder="transformer",
            dtype=torch.float16, quantization_config=BitsAndBytesConfig(load_in_8bit=True),
        )
        offload = "balanced"
    elif profile == "cosmos3-fp8":
        if torch.cuda.get_device_capability() < (8, 9):
            raise ValueError("Cosmos3 FP8 requires a native FP8 GPU. Use cosmos3-bf16 on A100.")
        kwargs["device_map"] = "cuda"
        offload = "gpu"
    elif profile == "mochi-bf16":
        kwargs["variant"] = "bf16"
        offload = "transformer_block_2"
    elif profile == "cosmos3-bf16":
        offload = "transformer_block_2"
    else:
        offload = "sequential"

    pipe = DiffusionPipeline.from_pretrained(repo, **kwargs)
    if offload == "transformer_block_2":
        pipe.transformer.enable_group_offload(
            onload_device=torch.device("cuda"), offload_device=torch.device("cpu"),
            num_blocks_per_group=2, offload_type="block_level",
        )
        pipe.vae.to("cuda")
        if profile == "mochi-bf16":
            pipe.text_encoder.to("cuda")
    elif offload == "sequential":
        pipe.enable_sequential_cpu_offload()
    pipe.vae.enable_tiling()

    if profile.startswith("cosmos3"):
        from diffusers import UniPCMultistepScheduler

        pipe.scheduler = UniPCMultistepScheduler.from_config(
            pipe.scheduler.config, flow_shift=10.0, use_karras_sigmas=False,
        )
    elif profile == "ltx2-distilled":
        from diffusers import FlowMatchEulerDiscreteScheduler

        pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(
            pipe.scheduler.config, use_dynamic_shifting=False, shift_terminal=None,
        )
    return pipe, offload


def main():
    args = parse_args()
    model, repo, height, width, frames, fps, steps, guidance = PROFILES[args.profile]
    settings = dict(
        height=height if args.height is None else args.height,
        width=width if args.width is None else args.width,
        num_frames=frames if args.frames is None else args.frames,
        num_inference_steps=steps if args.steps is None else args.steps,
        guidance_scale=guidance if args.guidance is None else args.guidance,
    )
    if min(settings["height"], settings["width"], settings["num_inference_steps"]) <= 0:
        raise ValueError("Height, width and inference steps must be positive.")
    if settings["num_frames"] < 2 or not math.isfinite(settings["guidance_scale"]) or settings["guidance_scale"] < 0:
        raise ValueError("Use at least two frames and finite, nonnegative guidance.")
    if model == "LTX-2" and (settings["height"] % 32 or settings["width"] % 32 or
                            (settings["num_frames"] - 1) % 8):
        raise ValueError("LTX-2 requires height/width multiples of 32 and 8n+1 frames.")
    if model == "Mochi 1" and (settings["height"] % 16 or settings["width"] % 16 or
                              (settings["num_frames"] - 1) % 6):
        raise ValueError("Mochi requires height/width multiples of 16 and 6n+1 frames.")
    if model == "Cosmos3 Nano" and (settings["height"] % 16 or settings["width"] % 16 or
                                   (settings["num_frames"] - 1) % 4):
        raise ValueError("Cosmos3 Nano requires height/width multiples of 16 and 4n+1 frames.")
    if args.profile == "ltx2-distilled" and (
        settings["num_inference_steps"] != 8 or settings["guidance_scale"] != 1 or args.negative_prompt
    ):
        raise ValueError("Use 8 distilled steps, guidance 1 and an empty negative prompt with this checkpoint.")
    with args.csv.open(encoding="utf-8-sig", newline="") as stream:
        prompts = {int(row["prompt_id"]): row["prompt_text"].strip() for row in csv.DictReader(stream)}
    for pid in args.prompt_id:
        if not prompts.get(pid):
            raise ValueError(f"Prompt {pid} is missing or empty in {args.csv}.")

    # Public checkpoints do not need Colab to request access to a stored secret.
    token = os.environ.get("HF_TOKEN")
    if not token:
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    elif model == "Cosmos3 Nano":
        # The guardrail loader authenticates with the Hub's standard environment token.
        os.environ.pop("HF_HUB_DISABLE_IMPLICIT_TOKEN", None)
    import torch
    from diffusers.utils import export_to_video
    from huggingface_hub import hf_hub_download, model_info
    from huggingface_hub.errors import GatedRepoError

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported(including_emulation=False):
        raise ValueError("Select a CUDA GPU with native BF16 support such as L4, A100 or H100.")
    if model == "Cosmos3 Nano":
        if importlib.util.find_spec("cosmos_guardrail") is None:
            raise ValueError("Install cosmos_guardrail before downloading Cosmos3 weights.")
        if not token:
            raise ValueError("Set HF_TOKEN with access to nvidia/Cosmos-1.0-Guardrail.")
        try:
            hf_hub_download("nvidia/Cosmos-1.0-Guardrail", "blocklist/custom/branding", token=token)
        except GatedRepoError as error:
            raise ValueError("HF_TOKEN needs access to nvidia/Cosmos-1.0-Guardrail.") from error
    token = token or False
    revision = model_info(repo, revision=args.revision, token=token).sha
    backend_settings = settings.copy()
    if model == "LTX-2":
        backend_settings["frame_rate"] = fps
    if model == "Cosmos3 Nano":
        backend_settings["fps"] = fps
    if args.negative_prompt is not None:
        backend_settings["negative_prompt"] = args.negative_prompt
    if args.profile == "ltx2-distilled":
        from diffusers.pipelines.ltx2.utils import DISTILLED_SIGMA_VALUES

        backend_settings.update(sigmas=DISTILLED_SIGMA_VALUES, audio_guidance_scale=1.0)

    precision = {"mochi-int8": "int8-weights/fp16", "cosmos3-fp8": "fp8-mixed"}.get(args.profile, "bf16")
    run_settings = {
        **backend_settings, "fps": fps, "profile": args.profile, "precision": precision,
        "audio_exported": False,
    }
    if model == "Cosmos3 Nano":
        run_settings.update(flow_shift=10.0, prompt_upsampled=False)
    args.output.mkdir(parents=True, exist_ok=True)
    pipe = None
    for pid in dict.fromkeys(args.prompt_id):
        prompt = prompts[pid]
        signature = json.dumps([revision, args.prompt_set, prompt, run_settings], sort_keys=True)
        tag = hashlib.sha256(signature.encode()).hexdigest()[:12]
        stem = f"{args.run_label}-{args.method}-{args.profile}-p{pid}-s{args.seed}-{tag}"
        video = args.output / f"{stem}.mp4"
        sidecar = video.with_suffix(".json")
        if video.exists() and sidecar.exists():
            prior = json.loads(sidecar.read_text(encoding="utf-8"))
            if prior["video_sha256"] != hashlib.sha256(video.read_bytes()).hexdigest():
                raise ValueError(f"Existing output checksum mismatch: {video}")
            print("Already complete:", video, flush=True)
            continue
        if pipe is None:
            print(f"Loading {repo}@{revision} on {torch.cuda.get_device_name()}", flush=True)
            setup_start = time.perf_counter()
            pipe, offload = load_pipeline(args.profile, repo, revision, torch, token)
            setup_seconds = time.perf_counter() - setup_start
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        try:
            with torch.inference_mode():
                output = pipe(
                    prompt=prompt, generator=torch.Generator("cuda").manual_seed(args.seed),
                    **backend_settings,
                )
        except ValueError as error:
            if model != "Cosmos3 Nano" or not str(error).startswith("Cosmos Guardrail detected unsafe "):
                raise
            print(f"Rejected by Cosmos guardrail: {stem}. {error}", flush=True)
            continue
        images = output.video if model == "Cosmos3 Nano" else output.frames[0]
        pending_video = video.with_suffix(".partial.mp4")
        pending_json = sidecar.with_suffix(".partial.json")
        try:
            export_to_video(images, str(pending_video), fps=fps, macro_block_size=1)
            meta = {
                "method": args.method, "prompt_set": args.prompt_set, "prompt_id": pid,
                "prompt_text": prompt, "model_name": model, "model_version": f"{repo}@{revision}",
                "seed": args.seed, "video_sha256": hashlib.sha256(pending_video.read_bytes()).hexdigest(),
                "settings": {
                    **run_settings, "actual_frames": len(images), "offload": offload,
                    "gpu": torch.cuda.get_device_name(),
                    "peak_allocated_gib": torch.cuda.max_memory_allocated() / 2**30,
                    "model_setup_seconds": setup_seconds,
                    "generation_and_export_seconds": time.perf_counter() - start,
                    "versions": {package: importlib.metadata.version(package)
                                 for package in ("diffusers", "transformers", "torch", "accelerate")},
                },
            }
            pending_json.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
            pending_video.replace(video)
            pending_json.replace(sidecar)
        finally:
            pending_video.unlink(missing_ok=True)
            pending_json.unlink(missing_ok=True)
        print("Saved:", video, flush=True)
        del images, output


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
