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

Initialization imports [prompts.csv](data/metadata/prompts.csv), the sole prompt source, containing 50 prompts. It never restores the old snapshot implicitly and refuses to overwrite an existing database.

Existing databases: run `python -m database.create_database migrate`, which creates a `.db.bak` backup and rebuilds the schema while preserving records. Then run `python -m database.create_database import-prompts` to import the current CSV. Prompts already used by a generation cannot change; keep their original records for provenance. Migration refuses to overwrite an existing backup. To restore [database_records.json](data/metadata/database_records.json) into an absent database, use `python -m database.create_database restore`. Export the current database using `python -m database.create_database export`.

CSV imports validate headers, IDs, required text, and allowed values, and report row numbers for invalid data. They do not validate incompatible attribute combinations.

For CPU-only Windows/Linux installations, install PyTorch first:

```bash
python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
```

On Windows PowerShell, set `$env:PYTHONPATH = "src"` instead of using `export`.

## Processing and resuming

Set a finite `quality_threshold` and document its pilot-based rationale in [config/evaluation.json](config/evaluation.json). Choose an experiment name, frame interval, and criterion weights before processing. Once scored, that experiment name requires exactly the same configuration across videos. Use separate named configs for pilot and final evaluation.

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

Registration copies a manually generated video into the baseline/proposed directory and records its exact prompt, model, optional seed, and settings. Extraction is atomic: failed extraction removes new frames and rolls back its records. Existing extracted frames are reused by `run`. Scoring downloads MUSIQ weights on first use and records checkpoint/runtime information, image hashes, and scores in a separate scoring run. Review uses that run's saved threshold and weights, verifies image hashes, and saves every completed review immediately, including nonmatching pairs. Repeating review resumes unfinished work. The winner is selected only after all candidate pairs have been reviewed; ties use image IDs. Selected pairs reference original images; files are not copied.

Images are inspected in an external image viewer. There is no browser gallery or automatic tattoo recognition. See [the scoring rubric](docs/SCORING_RUBRIC.md) for rating guidance.

## Tests

The standard-library tests do not require PyTorch, OpenCV, model downloads, or videos:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
