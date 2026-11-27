"""Import generated MP4s and export reviewed frame pairs."""

import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from database.create_database import (
    ROOT_DIRECTORY as ROOT,
    connect,
    load_allowed_values,
    load_prompts,
    save_records,
)
from database.process_video import CRITERIA, digest


def import_clip(db, sidecar):
    if sidecar.resolve().parent == ROOT / "data/videos/baseline" and sidecar.name.startswith("pilot-"):
        archived = ROOT / "data/videos/model_selection" / sidecar.name
        if not sidecar.exists() and archived.is_file():
            sidecar = archived
    run_name = sidecar.stem
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", run_name):
        raise ValueError("Use a unique lowercase run name for the MP4 and JSON.")
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("The sidecar must contain a JSON object.")
    method = record.get("method")
    prompt_set = record.get("prompt_set", "dataset")
    prompt_number = record.get("prompt_id")
    seed = record.get("seed")
    if method not in ("baseline", "proposed") or prompt_set not in ("dataset", "model_selection"):
        raise ValueError("Invalid method or prompt set.")
    if type(prompt_number) is not int or prompt_number <= 0:
        raise ValueError("prompt_id must be a positive integer.")
    if seed is not None and (type(seed) is not int or not 0 <= seed < 2**63):
        raise ValueError("seed must be a nonnegative SQLite integer or null.")
    for key in ("prompt_text", "model_name", "model_version"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"Missing {key}.")
    if not isinstance(record.get("settings"), dict):
        raise ValueError("settings must be a JSON object.")
    source = sidecar.with_suffix(".mp4")
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError(f"Missing or empty video: {source}")
    video_hash = digest(source)
    if record.get("video_sha256") != video_hash:
        raise ValueError(f"Video SHA-256 disagrees with {sidecar}.")

    prompt_id = prompt_number
    if prompt_set == "model_selection":
        # The pilot CSV reuses IDs from the dataset CSV for different text.
        prompt_id += 1000
        pilot_csv = ROOT / "data/metadata/model_selection_prompts.csv"
        if db.execute("SELECT 1 FROM prompt WHERE prompt_id=?", (prompt_id,)).fetchone() is None:
            load_prompts(db, load_allowed_values(db), path=pilot_csv, id_offset=1000)

    phase = record.get("study_phase")
    if phase is None:
        phase = "model_selection" if prompt_set == "model_selection" else method
    allowed_phases = ("model_selection", "duration_test") if prompt_set == "model_selection" else (method,)
    if phase not in allowed_phases:
        raise ValueError("Study phase does not match the prompt set and method.")
    destination = ROOT / "data/videos" / phase / source.name
    video_path = destination.relative_to(ROOT).as_posix()
    settings = {
        **record["settings"], "method": method, "prompt_set": prompt_set,
        "source_prompt_id": prompt_number, "video_sha256": video_hash,
    }
    settings_json = json.dumps(settings, sort_keys=True, allow_nan=False)
    values = (prompt_id, record["model_name"], record["model_version"], seed, settings_json)
    copied = False
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            prompt = db.execute("SELECT prompt_text FROM prompt WHERE prompt_id=?", (prompt_id,)).fetchone()
            if prompt is None or prompt["prompt_text"] != record["prompt_text"]:
                raise ValueError(f"Prompt text does not match {prompt_set} prompt {prompt_number}.")
            legacy_path = f"data/videos/{method}/{source.name}"
            existing = db.execute(
                """SELECT generation_id, prompt_id, model_name, model_version,
                          generation_seed, settings_json, video_path
                   FROM generation WHERE video_path IN (?, ?)
                   ORDER BY video_path=? DESC LIMIT 1""",
                (video_path, legacy_path if phase == "model_selection" else video_path, video_path),
            ).fetchone()
            if existing and tuple(existing)[1:-1] != values:
                raise ValueError(f"Run name already registered with different settings: {run_name}")
            if destination.exists():
                if digest(destination) != video_hash:
                    raise ValueError(f"Run name already has different video bytes: {run_name}")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
                    staged_video = Path(directory) / source.name
                    shutil.copyfile(source, staged_video)
                    if digest(staged_video) != video_hash:
                        raise ValueError("Video changed while copying.")
                    staged_video.replace(destination)
                    copied = True
            if existing:
                generation_id = existing["generation_id"]
                if existing["video_path"] != video_path:
                    db.execute("UPDATE generation SET video_path=? WHERE generation_id=?", (video_path, generation_id))
            else:
                cursor = db.execute(
                    """INSERT INTO generation
                       (prompt_id, model_name, model_version, generation_seed, settings_json, video_path)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (*values, video_path),
                )
                generation_id = cursor.lastrowid
    except BaseException:
        if copied:
            destination.unlink(missing_ok=True)
        raise
    save_records(db)
    return generation_id


def export_pairs(db, experiment, output, method=None):
    runs = {}
    for run in db.execute(
        """SELECT review_run.*, scoring_run.config_json, scoring_run.provenance_json
           FROM review_run JOIN scoring_run USING (scoring_run_id)
           WHERE status='complete' ORDER BY scoring_run_id"""
    ):
        if json.loads(run["config_json"])["experiment_name"] == experiment:
            runs[run["generation_id"]] = run

    if output.exists():
        raise ValueError(f"Export destination already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        staging = Path(directory) / "pairs"
        (staging / "frames").mkdir(parents=True)
        count = 0
        with (staging / "pairs.jsonl").open("w", encoding="utf-8") as manifest:
            for generation_id, run in runs.items():
                if run["selected_pair_id"] is None:
                    continue
                pair = db.execute(
                    """SELECT * FROM image_pairs
                       WHERE pair_id=? AND scoring_run_id=? AND same_tattoo=1""",
                    (run["selected_pair_id"], run["scoring_run_id"]),
                ).fetchone()
                if pair is None:
                    raise ValueError("Selected pair is missing or belongs to another review.")
                generation = db.execute(
                    """SELECT generation.*, prompt.prompt_text
                       FROM generation JOIN prompt USING (prompt_id) WHERE generation_id=?""",
                    (generation_id,),
                ).fetchone()
                settings = json.loads(generation["settings_json"])
                if method is not None and settings["method"] != method:
                    continue
                frames = db.execute(
                    """SELECT image.*, image_score.score, image_score.sha256
                       FROM image JOIN image_score USING (image_id)
                       WHERE scoring_run_id=? AND image_id IN (?, ?) ORDER BY image_id""",
                    (run["scoring_run_id"], pair["image_id_1"], pair["image_id_2"]),
                ).fetchall()
                if len(frames) != 2:
                    raise ValueError("Selected pair is missing frame scores.")
                frame_records = []
                clip_key = f"{settings['method']}-{Path(generation['video_path']).stem}"
                for frame in frames:
                    path = Path("frames") / f"{clip_key}-f{frame['frame_number']:06d}.png"
                    shutil.copyfile(ROOT / frame["image_path"], staging / path)
                    if digest(staging / path) != frame["sha256"]:
                        raise ValueError(f"Image {frame['image_id']} changed since scoring.")
                    frame_records.append({
                        "path": path.as_posix(), "frame_number": frame["frame_number"],
                        "musiq": frame["score"], "sha256": frame["sha256"],
                    })
                entry = {
                    "person_id": clip_key, "synthetic": True, "method": settings["method"],
                    "prompt_set": settings.get("prompt_set", "dataset"),
                    "prompt_id": settings.get("source_prompt_id", generation["prompt_id"]),
                    "prompt_text": generation["prompt_text"],
                    "model_name": generation["model_name"], "model_version": generation["model_version"],
                    "seed": generation["generation_seed"], "video_path": generation["video_path"],
                    "generation_settings": settings, "frames": frame_records,
                    "scoring_run_id": run["scoring_run_id"],
                    "evaluation": json.loads(run["config_json"]),
                    "scoring_provenance": json.loads(run["provenance_json"]),
                    "review": {key: pair[key] for key in (*CRITERIA, "total_score")},
                }
                manifest.write(json.dumps(entry, ensure_ascii=False) + "\n")
                count += 1
        if not count:
            raise ValueError(f"No approved frame pairs for experiment {experiment!r}.")
        staging.rename(output)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("import")
    ingest.add_argument("sidecars", type=Path, nargs="+")
    export = commands.add_parser("export")
    export.add_argument("--experiment", required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--method", choices=("baseline", "proposed"))
    args = parser.parse_args()
    with closing(connect()) as db:
        if args.command == "import":
            for sidecar in args.sidecars:
                print(f"{sidecar.stem}: generation {import_clip(db, sidecar)}")
        else:
            count = export_pairs(db, args.experiment, args.output, args.method)
            print(f"Exported {count} pairs to {args.output}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, sqlite3.Error) as error:
        raise SystemExit(str(error))
