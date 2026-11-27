# TattooGen · Baseline and proposed datasets

## Completed work

### Model selection

We selected LTX-2 19B Dev FP8. It preserved the rose tattoo across usable frames in the shared-prompt pilot. The Cosmos3 pair came from a different prompt. The [model-selection report](docs/MODEL_EVALUATION.md) records all three outcomes.

We archived the three model-selection clips and sidecars in [data/videos/model_selection](data/videos/model_selection/) and the two selected pilot pairs in [data/pairs/model_selection](data/pairs/model_selection/). The pilot manifest preserves prompt IDs, seeds, ratings, and file hashes.

### Duration test

We ran [01_ltx2_duration_test.ipynb](notebooks/01_ltx2_duration_test.ipynb) on prompts 1–3 from the model-selection prompt set. The recipe fixed seed 42, resolution 768 × 512, 24 fps, and 40 steps, and compared 49 and 65 frames.

All six clips completed on an L4. Mean generation and export time was 417.7 seconds at 49 frames and 521.7 seconds at 65 frames. The shorter recipe saved 19.9% on average and was faster on each prompt. At these averages, 50 clips would take about 5h 48m or 7h 15m, respectively, plus setup, interruptions, and retries. [Duration test clips and sidecars](https://drive.google.com/drive/folders/1rS7bj-mB4U088nJ-NN2Ld60uAfhYXxzV)

| Prompt | 49 frames, MUSIQ at frames 0, 18, 36 | 65 frames, MUSIQ at frames 0, 18, 36, 54 |
|---|---|---|
| 1 · Rose close-up | 64.62, 59.71, 58.67 | 60.40, 63.01, 61.27, 62.00 |
| 2 · Moving forearm | 59.87, 58.04, 56.69 | 51.84, 67.35, 61.23, 57.11 |
| 3 · Wide walking shot | 57.09, 49.02, 48.62 | 53.56, 43.23, 50.77, 51.75 |

The cutoff of 65 left zero clips with two eligible frames at either length. At an exploratory cutoff of 58, both lengths had two of three clips with two or more eligible frames. Candidate eligibility comes before pair review. In an AI-assisted visual check, the 49-frame rose and forearm clips kept their designs recognizable across samples, and the 65-frame forearm clip had more hand occlusion. We selected 49 frames for the baseline. The duration test used three paired development prompts.

### Baseline generation and MUSIQ

We ran [02_ltx2_baseline_batch.ipynb](notebooks/02_ltx2_baseline_batch.ipynb) on the 50 [dataset prompts](data/metadata/prompts.csv) with the 49-frame LTX-2 recipe. All 50 MP4s were imported into [data/videos/baseline](data/videos/baseline/), where each clip has its original generation JSON. The frozen plan and original run outputs are in the [baseline run folder](https://drive.google.com/drive/folders/1Pm9y_abl7miwYU3ZHmTgcuqHrX7zXZ66). Extracted frames in `data/images/baseline/` are generated locally and ignored by Git.

All 50 baseline clips have raw MUSIQ scores in `SQLite/tattoo_gen.db` and its [JSON snapshot](data/metadata/database_records.json). The [raw scoring config](config/baseline-scoring.json) samples frames 0, 18, and 36 (0.00, 0.75, and 1.50 seconds) and applies no cutoff. The 150 scores range from 27.84 to 75.24 with a median of 60.74.

| Candidate cutoff | Passing frames | Clips with at least two passing frames | Candidate pairs per reviewer |
|---|---:|---:|---:|
| 58 | 92 / 150 | 34 / 50 | 66 |
| 60 | 79 / 150 | 29 / 50 | 53 |
| 65 | 52 / 150 | 19 / 50 | 29 |

### Review packet

We prepared [baseline-review.zip](data/review/baseline-review.zip) with the exact prompts and original PNGs for 66 eligible pairs across 34 clips. The packet and submitted ratings are local files ignored by Git.

The [team review config](config/team-review.json) uses a MUSIQ cutoff of 58 for both phases, based on the development duration test. It uses the same 0.75-second frame interval and equal weights for consistency, visibility, prompt adherence, and useful variation. A pair qualifies for selection when all three reviewers can verify the same tattoo. For qualifying pairs, the coordinator tool takes the median per criterion and selects the highest weighted total per clip. Ties go to the lowest image IDs. Agreement and rejected pairs are preserved for analysis.

## Next · Independent baseline review

1. Give all three reviewers the same ZIP. Each person extracts it and opens `Review.html` in a browser. If you want a group practice session, use only the separate duration-test clips to align on the [rubric](docs/SCORING_RUBRIC.md) before opening the scored review round.
2. Enter your name and rate all 66 pairs independently. For verified matches, score each of the four criteria from 1 to 5. For No or uncertain, provide a short reason such as occlusion, tiny tattoo, changed design, or missing tattoo. The form shows the original frames and prompt. MUSIQ and other reviewers’ scores stay out of the form.
3. Use **Save progress file** if you need to finish later on another device or browser. Open the same packet and choose **Load saved file** to resume. When the form shows 66 of 66 complete, click **Download completed ratings** and send your JSON privately to the coordinator.
4. Keep the three original JSONs under `data/review/submissions/` or with the study record. From the repo root, run the commands below with the three actual filename paths.

```bash
PYTHONPATH=src python -m database.team_review collect \
  --ratings data/review/submissions/Chase-ratings.json \
            data/review/submissions/Anthony-ratings.json \
            data/review/submissions/Mikkel-ratings.json \
  --output data/review/baseline-summary.json

PYTHONPATH=src python -m database.dataset export \
  --experiment ltx2-team-review-v1 --method baseline --output data/pairs/baseline
```

The collector checks that all three reviewers rated the same packet, reuses the existing MUSIQ scores and stores the consolidated review in SQLite. The summary includes split identity votes, reviewer notes, candidate ratings, frame scores, and clips with no winner. If no pair passes review, the summary still captures all clip outcomes and there is no dataset to export. Report pair yield out of all 50 planned clips.

## Then · Build and evaluate the proposed dataset

1. Use the baseline summary to identify the most frequent failures. Separate clips with fewer than two MUSIQ-passing frames from clips that reached human review. Within human review, look for recurring identity, visibility, prompt adherence, or variation problems in the scores and notes.
2. Choose a targeted recipe change and test it on development prompts first. For example, test a guidance change if the requested tattoo motif is often missing. Keep the original 50 prompt texts and seeds if changing generation settings. A prompt rewrite requires versioned prompts and a mapping to the baseline IDs.
3. Add the chosen change to the pinned native FP8 generation recipe and regenerate the same 50 scenarios. The native notebook currently covers the baseline only. Register the new sidecars with `method` and `study_phase` set to `proposed`. Extract and score frames using the same sampling interval, MUSIQ checkpoint, and scoring environment. Record failures in the original 50-clip denominator.
4. Build the proposed review packet with the same team config. Replace `PROPOSED_RAW_EXPERIMENT` with the name used for the proposed MUSIQ scoring runs.

```bash
PYTHONPATH=src python -m database.team_review packet --phase proposed \
  --source PROPOSED_RAW_EXPERIMENT --output data/review/proposed-review.zip
```

5. Have the same three people independently rate the proposed pairs. Run the collector with `--phase proposed --source PROPOSED_RAW_EXPERIMENT`, the three new ratings files, and a new summary path. Export with `--experiment ltx2-team-review-v1 --method proposed --output data/pairs/proposed`.
6. Compare baseline and proposed by prompt ID. Report the fraction of frames passing MUSIQ, approved pairs per 50 planned clips, reviewer agreement, and the four human criteria for approved pairs.

## Reproducing completed work

The original [README](README.md) covers database setup. The Colab notebooks bundle the runner and prompt CSVs, with `SOURCE_REPO = None` using the bundled assets. They were run on an L4 with High RAM and use a Colab `HF_TOKEN` secret for the pinned [Gemma encoder](https://huggingface.co/google/gemma-3-12b-it-qat-q4_0-unquantized). Allow about 60 GiB of VM scratch for the checkpoints. After changing runner code or prompt CSVs, refresh notebook assets with `python notebooks/sync_colab_assets.py`. Use the same frozen plan and Drive output folder to resume interrupted generation.

On a machine with the imported clips and scored frames, rebuild the baseline review ZIP with:

```bash
PYTHONPATH=src python -m database.team_review packet --output data/review/baseline-review.zip
```
