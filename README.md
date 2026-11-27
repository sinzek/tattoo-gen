# Synthetic Tattoo Generation

University of Houston — Computational Biomedicine Lab

This research project evaluates text-to-video generation for synthetic tattoo-recognition imagery. It compares baseline and proposed generation methods, extracts video frames, scores perceptual quality with MUSIQ, and records manual reviews of candidate image pairs.

## Setup

Use a dedicated Python 3.11 or 3.12 environment. From the repository root:

```bash
python -m pip install -r requirements.txt
export PYTHONPATH=src
python -m database.create_database init
```

Initialization imports the 50 dataset prompts in [prompts.csv](data/metadata/prompts.csv). Imports from the earlier [model-selection CSV](data/metadata/model_selection_prompts.csv) use a separate ID range and retain the original source ID. Initialization refuses to overwrite an existing database. Restore the old snapshot explicitly if you need it.

Existing databases: run `python -m database.create_database migrate`, which creates a `.db.bak` backup and rebuilds the schema while preserving records. Then run `python -m database.create_database import-prompts` to import the current CSV. Prompts already used by a generation cannot change; keep their original records for provenance. Migration refuses to overwrite an existing backup. To restore [database_records.json](data/metadata/database_records.json) into an absent database, use `python -m database.create_database restore`. Export the current database using `python -m database.create_database export`.

CSV imports validate headers, IDs, required text, and allowed values, and report row numbers for invalid data. They do not validate incompatible attribute combinations.

For CPU-only Windows/Linux installations, install PyTorch first:

```bash
python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
```

On Windows PowerShell, set `$env:PYTHONPATH = "src"` instead of using `export`.

## Processing and resuming

The [model evaluation guide](docs/MODEL_EVALUATION.md) records the benchmark evidence, quantization options and batch generation commands. Each included pilot MP4 has a matching JSON with its exact prompt, seed, settings, and SHA-256.

Import a generated MP4 by keeping its matching JSON beside it. Imports verify the exact CSV prompt and MP4 checksum, and return the same generation ID on a retry. Run imports and processing from one working copy so generation IDs and reviews stay together.

```bash
python -m database.dataset import data/videos/baseline/pilot-ltx2-p1-s42-dev-fp8.json
python -m database.process_video prepare --generation-id 1
```

Use the generation ID printed by the import. `prepare` extracts frames and scores them with MUSIQ. The default config allows exploratory scoring before a threshold has been chosen. For review, set a finite `quality_threshold` and document its pilot-based rationale. Choose an experiment name, frame interval, and criterion weights before scoring the reviewed cohort. Once scored, that experiment name requires exactly the same configuration across videos. Use a new experiment name when moving from exploratory scoring to review. The [pilot review config](config/pilot-review.json) records the exploratory cutoff and reviewer provenance.

```bash
python -m database.process_video run --config config/evaluation.json
# Resume a registered generation:
python -m database.process_video run --generation-id 1 --config config/evaluation.json
```

Individual stages are also available:

```bash
python -m database.process_video register
python -m database.process_video extract --generation-id 1
python -m database.process_video score --generation-id 1
python -m database.process_video review --scoring-run-id 1
```

Use the scoring-run ID printed by `prepare` or `score` for review. Compare the two images against the exact prompt printed before review. Pass the experiment name from the review configuration to the export command.

```bash
python -m database.dataset export --experiment model-selection-pilot --output data/pairs/pilot-replay
```

The export contains selected PNGs and a JSONL manifest with a clip-scoped synthetic person ID, original prompt, method, model, seed, frame hashes, MUSIQ scores and review ratings. Only completed reviews with a selected matching pair appear. Use `--method baseline` or `--method proposed` and different output directories to export the two phases from one shared evaluation config. If the dataset is split later, group by source prompt across phases and models to keep near-duplicate conditions together. The repository’s pilot pairs have exploratory, AI-assisted ratings.

Registration copies a manually generated video into the baseline/proposed directory and records its exact prompt, model, optional seed, and settings. If extraction fails, it removes the new frames and rolls back their records. Existing extracted frames are reused by `run` and `prepare`. Scoring downloads MUSIQ weights on first use and records checkpoint/runtime information, image hashes, and scores in a separate scoring run. Review uses that run's saved threshold and weights, verifies image hashes, and saves every completed review immediately, including nonmatching pairs. Repeating review resumes unfinished work. Selection runs after all candidate pairs have been reviewed and breaks ties by image ID. The database stores frame references. Dataset export copies the selected PNGs.

Images are inspected in an external image viewer. There is no browser gallery or automatic tattoo recognition. See [the scoring rubric](docs/SCORING_RUBRIC.md) for rating guidance.

## Tests

The standard-library tests do not require PyTorch, OpenCV, model downloads, or videos:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
