# Model selection and pilot results

We selected **LTX-2 19B Dev FP8** for the dataset. In the shared-prompt pilot, it produced a usable pair with the requested rose tattoo. Mochi 1 had no frames above the pilot MUSIQ cutoff, and Cosmos3 Nano produced a usable pair on a different prompt after its guardrail rejected the rose prompt. The LTX-2 recipe also ran on a Colab L4.

This report records the shortlist evidence and the three model-selection runs. The 49-frame duration decision, 50-prompt baseline, and three-reviewer dataset process are documented in the [study workflow](../README_proposed.md).

## Published evidence

Slides 6–9 of the [project presentation](https://docs.google.com/presentation/d/1uYtbvdzYfQf1ocIU4lEgR4RYMZI42q73agRsO-cXKfA/edit) report the November 14, 2026 WhatModel video scores. These are aggregate scores with reported uncertainty and mixed benchmark coverage. The paper results below provide additional context. Each uses its own evaluation protocol and score scale. [WhatModel methodology and source data](https://github.com/jakemanger/whatmodel)

| Shortlisted model | WhatModel, November 14 | Published result |
|---|---:|---|
| LTX-2 | 48.6 ± 1.7, four results | The LTX-2 paper reports fourth place in Artificial Analysis text-to-video on November 6, 2025 and 1.22 s per diffusion step on an H100 for 121 frames at 720p with CFG 1. [LTX-2 paper, §6.2–6.3](https://arxiv.org/html/2601.03233) |
| Mochi 1 | 39.5 ± 1.6, six results | VBench-Long overall 80.13, quality 82.64, semantic 70.08, and subject consistency 96.99. [Ren et al., ICCV 2025, Table 1](https://openaccess.thecvf.com/content/ICCV2025/papers/Ren_Turbo2K_Towards_Ultra-Efficient_and_High-Quality_2K_Video_Synthesis_ICCV_2025_paper.pdf) |
| Cosmos3 Nano | 51.3 ± 2.6, six results | Cosmos HUE text-to-video 87.6 overall and 92.5 for visual integrity. [NVIDIA Cosmos 3 report, Table 32](https://research.nvidia.com/labs/cosmos-lab/cosmos3/technical-report.pdf) |

## Pilot results

LTX-2 and Mochi 1 used model-selection prompt 1 (the rose tattoo) and seed 42. The Cosmos3 text guardrail rejected prompts 1 (rose on the upper arm) and 7 (compass on the calf). We sampled frames at one-second intervals and applied an exploratory MUSIQ cutoff of 65.0.

| Model and recipe | Clip | L4 time and memory | MUSIQ by frame | Pair result |
|---|---|---|---|---|
| LTX-2 Dev FP8 | 768 × 512, 121 frames at 24 fps | 827 s from launch to export, 21.77 GiB sampled device peak | 73.49, 70.12, 66.87, 60.88, 58.80, 55.57 | 3/6 passing. Frames 0 and 48 selected with 80/100 in an AI-assisted review. Later frames crop the design. |
| Mochi 1 BF16, transformer block offload | 640 × 384, 61 frames at 30 fps, 20 steps | 62 s model setup from cache, 592 s generation and export, 17.12 GiB allocated peak | 45.47, 61.19, 59.88 | 0/3 passing. The rose was visible and mostly dark. No pair met the cutoff. |
| Cosmos3 Nano BF16, transformer block offload | 576 × 320, 49 frames at 24 fps, 10 steps, prompt 2 | 243 s model setup including downloads, 642 s generation and export, 5.53 GiB allocated peak | 60.30, 65.14, 65.42 | 2/3 passing. Frames 24 and 48 selected with 65/100 in an AI-assisted review. The wolf is visible, with modest motion and a tighter shot than requested. |

Resolution, duration, step counts, and precision differed across recipes. The Cosmos3 clip used a different prompt, and the timing and memory columns use the measurements available for each run. These three clips supported a practical model choice for this project. The archived pair scores came from an AI-assisted pilot review. [Pilot clips and sidecars](../data/videos/model_selection/) · [Pilot pair manifest](../data/pairs/model_selection/pairs.jsonl)

## Precision options for follow-up

The pilot ran LTX-2 in FP8 and Mochi 1 and Cosmos3 Nano in BF16. A controlled comparison of precisions within each model remains open. The options below are follow-up experiments.

| Model | Pilot and reference configurations | Possible follow-up |
|---|---|---|
| LTX-2 | The archived 19B Dev FP8 run produced a 768 × 512, 121-frame clip in 827 s from launch, including model loading and export. Peak sampled device memory was 21.77 GiB on a Colab L4. The recorded backend requires L4 or newer FP8-capable hardware. | Benchmark the 8-step distilled checkpoint. This changes the checkpoint and denoising schedule. For a precision comparison, hold the Dev checkpoint family, model backend, dimensions, seed and scheduler fixed. The official native Dev artifacts are 43.3 GB in BF16 and 27.1 GB in FP8, before the text encoder. [LTX-2 weights](https://huggingface.co/Lightricks/LTX-2/tree/main) · [Diffusers LTX-2 recipes](https://huggingface.co/docs/diffusers/en/api/pipelines/ltx2) |
| Mochi 1 | The pilot used BF16 with transformer block offload. The Diffusers example uses CPU offload and VAE tiling and reports about 22 GB VRAM for 85 frames with its BF16 recipe. | Try documented BitsAndBytes INT8 for the transformer and T5 encoder. Compare actual elapsed time with BF16. Offloading and INT8 can reduce GPU memory while adding transfer or dequantization overhead. [Diffusers Mochi recipes](https://huggingface.co/docs/diffusers/en/api/pipelines/mochi) |
| Cosmos3 Nano | The pilot used BF16 with transformer block offload at 576 × 320. The documented vLLM-Omni 720p model uses about 46 GiB peak. | Try the official mixed FP8 checkpoint on a native-FP8 GPU with enough VRAM. Keep the vendor's mixed denoising schedule for multi-step video. NVIDIA reports PAIBench-G T2V of 79.40 for both BF16 and FP8, using different inference runtimes. Its throughput table covers image-to-video. [Cosmos3 FP8 model card](https://huggingface.co/nvidia/Cosmos3-Nano-FP8) · [Diffusers mixed FP8 notes](https://huggingface.co/docs/diffusers/en/api/pipelines/cosmos3) · [vLLM-Omni T2V profiles](https://docs.vllm.ai/projects/vllm-omni/en/v0.26.0/user_guide/examples/offline_inference/text_to_video/) |

Use the same development prompts and seeds within each precision comparison. Keep the scheduler, guidance, resolution, duration and output encoding fixed. Measure warm generation plus export seconds per clip, peak GPU memory and eligible pair yield. Report model setup time and failures separately. Colab can substitute an available GPU for a requested accelerator. Record the actual hardware on each run. [Colab resource limits](https://research.google.com/colaboratory/faq.html)

## Reproduce the model-selection pilot

The [pilot notebook](https://colab.research.google.com/drive/1PPHoYtFFk5cQB-bHr1jEvUmLJb6dDe82) was used to launch the Mochi and Cosmos trial jobs. To replay these pilot jobs, place this repo in the Colab runtime or upload `notebooks/generate_videos.py` and the desired CSV. Use a high-RAM GPU VM with enough local scratch for weights and keep the inference packages separate from the repository's CPU scoring environment.

```python
%pip install 'diffusers==0.43.0' 'transformers>=5,<6' 'accelerate>=1.10,<2' ftfy sentencepiece 'imageio[ffmpeg]' av
!nvidia-smi
```

Before a Cosmos run, install `cosmos_guardrail`, request access to NVIDIA's gated guardrail weights, and provide a Hugging Face read token for that account through `HF_TOKEN`. The generator checks this access before downloading the larger Cosmos3 checkpoint. If the Xet transfer stalls on uncached Cosmos shards, retry the download with `HF_HUB_DISABLE_XET=1` and a fresh cache directory. [Cosmos3 Diffusers setup](https://huggingface.co/docs/diffusers/en/api/pipelines/cosmos3) · [Gated guardrail weights](https://huggingface.co/nvidia/Cosmos-1.0-Guardrail)

In Colab, enable the `HF_TOKEN` secret for the notebook, then run this cell before generation.

```python
import os
from google.colab import userdata

os.environ["HF_TOKEN"] = userdata.get("HF_TOKEN")
```

From the repo root in the runtime, start with one prompt. The Mochi command uses the same input and seed as the archived LTX-2 pilot. The Cosmos command uses the seated forearm-tattoo prompt and the same seed. Both commands use shorter clips to fit the available L4. The LTX-2 pilot used the native one-stage FP8 recipe recorded in its sidecar. To replay it, use height and width divisible by 32. [Native LTX-2 notebook](https://colab.research.google.com/drive/16hXhYrB_0CCtTwU-0EFzpMNyOqnVVW1m)

```bash
python notebooks/generate_videos.py --profile mochi-bf16 --csv data/metadata/model_selection_prompts.csv --prompt-set model_selection --prompt-id 1 --seed 42 --height 384 --width 640 --frames 61 --steps 20 --run-label pilot --output /content/tattoo-pilot
python notebooks/generate_videos.py --profile cosmos3-bf16 --csv data/metadata/model_selection_prompts.csv --prompt-set model_selection --prompt-id 2 --seed 42 --height 320 --width 576 --frames 49 --steps 10 --run-label pilot --output /content/tattoo-pilot
```

Install `bitsandbytes` for `mochi-int8` or `diffusers[nvidia-modelopt]==0.43.0` for `cosmos3-fp8`. For gated weights, provide your existing Hugging Face access through the runtime environment's `HF_TOKEN`. The generator resolves and records a checkpoint SHA. Use `--revision` to replay it. Copy each completed MP4 and JSON together from the runtime, then import them as described in the [README](../README.md).
