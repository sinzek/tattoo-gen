"""Plan and run the native LTX-2 Dev FP8 generation jobs used by the Colab notebooks."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


REPOSITORY = "Lightricks/LTX-2"
CODE_REVISION = "e98f6d927d83c92ef2be6aec76c8440b19306e39"
WEIGHTS_REVISION = "dfcc2108383fe1aaa0584bdf55d368a4bdadd90c"
CHECKPOINT = "ltx-2-19b-dev-fp8.safetensors"
ENCODER = "google/gemma-3-12b-it-qat-q4_0-unquantized"
ENCODER_REVISION = "68f7ee4fbd59087436ada77ed2d62f373fdd4482"
RECIPE = {
    "height": 512, "width": 768, "fps": 24, "steps": 40, "guidance": 3.0,
    "audio_guidance": 7.0, "stg_layers": [29], "stg_scale": 1.0,
    "rescale": 0.7, "modality_scale": 3.0, "negative_prompt": "",
    "prompt_enhancement": False, "pipeline": "native_one_stage_fp8",
    "precision": "bf16", "quantization": "fp8-scaled-mm",
    "offloading": "text_encoder_disk_transformer_resident",
    "checkpoint_file": CHECKPOINT, "code_revision": CODE_REVISION,
    "encoder_repository": ENCODER, "encoder_revision": ENCODER_REVISION,
}


def make_plan(phase, csv_path, frames, prompt_ids, seed):
    if not 0 <= seed < 2**63:
        raise ValueError("Seed must be a nonnegative SQLite integer.")
    if not frames or len(frames) != len(set(frames)) or any(n < 9 or n % 8 != 1 for n in frames):
        raise ValueError("Use distinct frame counts of the form 8n+1, each at least 9.")
    with csv_path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    prompts = {int(row["prompt_id"]): row["prompt_text"].strip() for row in rows}
    if len(prompts) != len(rows) or not all(prompts.values()) or any(pid < 1 for pid in prompts):
        raise ValueError("The CSV must contain unique positive IDs and nonempty prompts.")
    if phase == "baseline":
        if set(prompts) != set(range(1, 51)) or prompt_ids or len(frames) != 1:
            raise ValueError("Baseline requires the 50 dataset prompts and one fixed frame count.")
        prompt_ids = sorted(prompts)
    elif not prompt_ids or len(frames) < 2:
        raise ValueError("The duration test needs prompt IDs and at least two frame counts.")
    if len(prompt_ids) != len(set(prompt_ids)) or not set(prompt_ids) <= set(prompts):
        raise ValueError("Requested prompt IDs must be distinct and present in the CSV.")
    jobs = []
    for index, pid in enumerate(prompt_ids):
        # Rotate lengths by prompt to spread first-job effects across lengths.
        offset = index % len(frames)
        for count in frames[offset:] + frames[:offset]:
            jobs.append({"prompt_id": pid, "prompt_text": prompts[pid], "seed": seed, "frames": count})
    return {
        "study_phase": phase,
        "prompt_set": "dataset" if phase == "baseline" else "model_selection",
        "model_version": f"{REPOSITORY}@{WEIGHTS_REVISION}",
        "recipe": RECIPE,
        "jobs": jobs,
    }


def file_hash(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def finished(path, expected):
    video = path.with_suffix(".mp4")
    if not path.exists():
        return False
    sidecar = json.loads(path.read_text())
    fields = ("study_phase", "prompt_set", "prompt_id", "prompt_text", "model_version", "seed")
    if (any(sidecar.get(key) != expected[key] for key in fields)
            or sidecar.get("settings", {}).get("frames") != expected["frames"]
            or not video.is_file() or file_hash(video) != sidecar.get("video_sha256")):
        raise ValueError(f"Existing output conflicts with this plan or has damaged files: {path}")
    return True


def open_pipeline():
    import torch
    from huggingface_hub import hf_hub_download, snapshot_download
    from ltx_core.quantization.fp8_scaled_mm import build_policy
    from ltx_pipelines.ti2vid_one_stage import TI2VidOneStagePipeline
    from ltx_pipelines.utils.blocks import PromptEncoder
    from ltx_pipelines.utils.model_paths import ModelPaths
    from ltx_pipelines.utils.types import OffloadMode

    if not torch.cuda.is_available() or torch.cuda.get_device_capability() < (8, 9):
        raise RuntimeError("The tested native FP8 backend requires an L4 (SM89) or newer supported GPU.")
    device = torch.device("cuda")
    fp8 = torch.ones((16, 16), device=device, dtype=torch.bfloat16).to(torch.float8_e4m3fn)
    scale = torch.ones((), device=device)
    torch._scaled_mm(fp8, fp8.t(), scale_a=scale, scale_b=scale, out_dtype=torch.bfloat16)
    torch.cuda.synchronize()

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError("Enable the HF_TOKEN Colab secret for the gated Gemma encoder.")
    print("Checking Gemma access and preparing pinned checkpoint files", flush=True)
    hf_hub_download(ENCODER, "config.json", revision=ENCODER_REVISION, token=token)
    checkpoint = hf_hub_download(REPOSITORY, CHECKPOINT, revision=WEIGHTS_REVISION, token=token)
    encoder = snapshot_download(
        ENCODER, revision=ENCODER_REVISION, token=token, max_workers=2,
        allow_patterns=["*.json", "*.model", "*.safetensors", "*.jinja"],
    )
    paths = ModelPaths.from_monolith(checkpoint, gemma_root=encoder)
    pipeline = TI2VidOneStagePipeline(
        model_paths=paths, loras=[], device=device,
        quantization=build_policy(checkpoint), offload_mode=OffloadMode.NONE,
    )
    pipeline.prompt_encoder = PromptEncoder(
        paths, dtype=torch.bfloat16, device=device, offload_mode=OffloadMode.DISK,
    )
    return pipeline


def render(pipeline, job, path):
    import torch
    from ltx_core.components.guiders import MultiModalGuiderParams
    from ltx_core.model.video_vae import AUTO_TILING, get_video_chunks_number
    from ltx_pipelines.utils.media_io import encode_video

    def guider(scale):
        return MultiModalGuiderParams(
            cfg_scale=scale, stg_scale=RECIPE["stg_scale"], rescale_scale=RECIPE["rescale"],
            modality_scale=RECIPE["modality_scale"], skip_step=0, stg_blocks=RECIPE["stg_layers"],
        )

    torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    with torch.inference_mode():
        result = pipeline(
            prompt=job["prompt_text"], seed=job["seed"], negative_prompt=RECIPE["negative_prompt"],
            height=RECIPE["height"], width=RECIPE["width"], num_frames=job["frames"],
            frame_rate=RECIPE["fps"], num_inference_steps=RECIPE["steps"],
            video_guider_params=guider(RECIPE["guidance"]),
            audio_guider_params=guider(RECIPE["audio_guidance"]), images=[],
            enhance_prompt=False, tiling_config=AUTO_TILING, max_batch_size=1,
        )
        if result.num_frames != job["frames"]:
            raise RuntimeError(f"Pipeline returned {result.num_frames} frames for requested {job['frames']}.")
        encode_video(
            video=result.video, fps=RECIPE["fps"], audio=result.audio, output_path=str(path),
            video_chunks_number=get_video_chunks_number(result.num_frames, result.tiling_config),
        )
        torch.cuda.synchronize()
    return {
        **RECIPE, "frames": job["frames"], "actual_frames": result.num_frames,
        "generation_and_export_seconds": time.perf_counter() - start,
        "gpu": torch.cuda.get_device_name(),
        "peak_allocated_gib": torch.cuda.max_memory_allocated() / 2**30,
        "torch": str(torch.__version__),
    }


def run_plan(plan, output, continue_on_error):
    output.mkdir(parents=True, exist_ok=True)
    frozen = output / "plan.json"
    if frozen.exists():
        if json.loads(frozen.read_text()) != plan:
            raise ValueError("This output folder has a different frozen plan. Choose a fresh folder.")
    else:
        with tempfile.TemporaryDirectory(dir=output) as temporary:
            staged = Path(temporary) / frozen.name
            staged.write_text(json.dumps(plan, indent=2) + "\n")
            staged.replace(frozen)
    pending = []
    phase = plan["study_phase"]
    for job in plan["jobs"]:
        stem = f"{phase.replace('_', '-')}-ltx2-p{job['prompt_id']:03}-s{job['seed']}-f{job['frames']}"
        sidecar = output / f"{stem}.json"
        expected = {
            **job, "study_phase": phase, "prompt_set": plan["prompt_set"],
            "model_version": plan["model_version"],
        }
        if finished(sidecar, expected):
            print("Verified completed job", stem, flush=True)
        else:
            pending.append((sidecar, expected))
    if not pending:
        print("All jobs complete.")
        return

    setup_start = time.perf_counter()
    pipeline = open_pipeline()
    setup_seconds = time.perf_counter() - setup_start
    failures = 0
    for sidecar, job in pending:
        print("Generating", sidecar.stem, flush=True)
        attempt_start = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(dir=output) as temporary:
                video = Path(temporary) / sidecar.with_suffix(".mp4").name
                settings = render(pipeline, job, video)
                if not video.stat().st_size:
                    raise RuntimeError("Encoder wrote an empty video.")
                settings["session_setup_seconds"] = setup_seconds
                record = {
                    **job, "method": "baseline", "model_name": "LTX-2",
                    "video_sha256": file_hash(video), "settings": settings,
                }
                record.pop("frames")
                metadata = video.with_suffix(".json")
                metadata.write_text(json.dumps(record, indent=2) + "\n")
                video.replace(sidecar.with_suffix(".mp4"))
                metadata.replace(sidecar)
        except Exception as error:
            failures += 1
            with (output / "failures.jsonl").open("a", encoding="utf-8") as file:
                file.write(json.dumps({
                    "job": sidecar.stem, "error": str(error), "time": time.time(),
                    "attempt_seconds": time.perf_counter() - attempt_start,
                }) + "\n")
            if not continue_on_error:
                raise
            print(f"Failed {sidecar.stem}: {error}", flush=True)
        else:
            print("Saved", sidecar.name, flush=True)
    if failures:
        raise RuntimeError(f"{failures} jobs failed. See failures.jsonl and rerun to retry them.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("duration_test", "baseline"))
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frames", nargs="+", type=int, required=True)
    parser.add_argument("--prompt-ids", nargs="+", type=int)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()
    plan = make_plan(args.phase, args.csv, args.frames, args.prompt_ids, args.seed)
    if args.run:
        run_plan(plan, args.output, args.continue_on_error)
    else:
        print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
