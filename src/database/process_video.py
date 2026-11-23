# Register videos, extract frames, score with MUSIQ, and resume pair reviews.
# Each scoring run freezes its configuration, checkpoint provenance, and image hashes.

import itertools
import json
import math
import shutil
import sqlite3
import uuid
from pathlib import Path

import hashlib
import platform
import argparse
from importlib.metadata import version

from database.create_database import ROOT_DIRECTORY as ROOT, connect, save_records


def read_number(label, integer=False, default=None):
    text = input(label).strip()

    if not text and default is not None:
        return default

    value = int(text) if integer else float(text)

    if not math.isfinite(value):
        raise ValueError("Enter a finite number.")

    return value


def register_video(db):
    prompt_id = read_number("Prompt ID: ", integer=True)
    prompt = db.execute(
        "SELECT prompt_text FROM prompt WHERE prompt_id = ?",
        (prompt_id,),
    ).fetchone()

    if prompt is None:
        raise ValueError("Prompt ID not found.")

    print("\nPrompt:", prompt["prompt_text"])
    if input("Did you use this exact prompt? [y/n]: ").lower().strip() != "y":
        raise ValueError("Add the actual prompt to the database first.")

    model = input("Model name: ").strip()
    version = input("Model version: ").strip()
    seed_text = input("Seed (blank if unavailable): ").strip()
    seed = int(seed_text) if seed_text else None
    method = input("Method [baseline/proposed]: ").lower().strip()
    notes = input("Other settings or notes: ").strip()

    if not model or not version:
        raise ValueError("Model name and version are required.")
    if seed is not None and seed < 0:
        raise ValueError("Seed cannot be negative.")
    if method not in ("baseline", "proposed"):
        raise ValueError("Method must be baseline or proposed.")

    source = Path(
        input("Downloaded video path: ").strip().strip('"').strip("'")
    ).expanduser()
    if not source.is_absolute():
        source = ROOT / source
    if not source.is_file():
        raise ValueError("Video file not found.")

    destination = ROOT / "data/videos" / method
    destination.mkdir(parents=True, exist_ok=True)
    destination = destination / f"{uuid.uuid4().hex}{source.suffix}"
    shutil.copy2(source, destination)

    try:
        with db:
            cursor = db.execute(
                """INSERT INTO generation
                   (prompt_id, model_name, model_version, generation_seed,
                    video_path, settings_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    prompt_id, model, version, seed,
                    destination.relative_to(ROOT).as_posix(),
                    json.dumps({"method": method, "notes": notes}),
                ),
            )
            generation_id = cursor.lastrowid
    except BaseException:
        destination.unlink(missing_ok=True)
        raise

    save_records(db)
    print("Saved generation:", generation_id)
    return generation_id, destination, method


def extract_frames(db, generation_id, video, method, interval):
    import cv2
    folder = (
        ROOT / "data/images" / method / f"generation_{generation_id:03d}"
    )
    folder.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    written = []

    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not capture.isOpened() or not math.isfinite(fps) or fps <= 0:
            raise ValueError("Cannot read this video's FPS.")

        step = max(1, round(interval * fps))
        frame_number = 0

        with db:
            while True:
                success, frame = capture.read()
                if not success:
                    break

                if frame_number % step == 0:
                    path = folder / f"frame_{frame_number:06d}.png"
                    if path.exists():
                        raise ValueError(f"File already exists: {path}")

                    written.append(path)
                    if not cv2.imwrite(str(path), frame):
                        raise ValueError("Could not save frame.")


                    db.execute(
                        """INSERT INTO image
                           (generation_id, frame_number, image_path)
                           VALUES (?, ?, ?)""",
                        (
                            generation_id, frame_number,
                            path.relative_to(ROOT).as_posix(),
                        ),
                    )
                    print(f"Extracted frame {frame_number}")

                frame_number += 1

            expected = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            if frame_number == 0:
                raise ValueError("No frames could be read.")
            if math.isfinite(expected) and expected > frame_number + 1:
                raise ValueError("Video decoding stopped early.")

            db.execute("UPDATE generation SET frame_interval=? WHERE generation_id=?", (interval,generation_id))

    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    finally:
        capture.release()

    save_records(db)
    print("Images saved in:", folder)


CRITERIA = ("consistency", "visibility", "prompt_adherence", "variation")


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_config(path):
    config = json.loads(Path(path).read_text())
    for key in ("quality_threshold", "frame_interval"):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Set a finite {key} in the experiment config before processing.")
    if config["frame_interval"] <= 0:
        raise ValueError("frame_interval must be positive.")
    if config.get("metric") != "musiq" or config.get("device") != "cpu":
        raise ValueError("Supported metric/device: musiq/cpu.")
    weights = config.get("weights", {})
    if set(weights) != set(CRITERIA) or any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) or v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Provide nonnegative criterion weights with a positive sum.")
    if not config.get("experiment_name") or not str(config.get("threshold_rationale", "")).strip():
        raise ValueError("Experiment name and threshold rationale are required.")
    return config


def freeze_config(db, config):
    # A named experiment must retain its exact configuration across generations.
    for row in db.execute("SELECT config_json FROM scoring_run"):
        old = json.loads(row[0])
        if old.get("experiment_name") == config["experiment_name"] and old != config:
            raise ValueError("This experiment already has a different frozen config. Use a new experiment name.")


def generation_info(db, generation_id):
    row = db.execute("SELECT * FROM generation WHERE generation_id=?", (generation_id,)).fetchone()
    if row is None:
        raise ValueError("Generation not found.")
    if not row["video_path"]:
        raise ValueError("Generation has no registered video path.")
    method = json.loads(row["settings_json"])["method"]
    if method not in ("baseline", "proposed"):
        raise ValueError("Invalid generation method.")
    return row, ROOT / row["video_path"], method


def score_frames(db, generation_id, config):
    freeze_config(db, config)
    generation, _, _ = generation_info(db, generation_id)
    if generation["frame_interval"] != config["frame_interval"]:
        raise ValueError("Config interval differs from extracted frames.")
    frames = db.execute("SELECT * FROM image WHERE generation_id=? ORDER BY image_id", (generation_id,)).fetchall()
    if not frames:
        raise ValueError("Extract frames first.")
    import torch
    import pyiqa
    metric = pyiqa.create_metric("musiq", device="cpu")
    metric.eval()
    state_hash = hashlib.sha256()
    for name, tensor in sorted(metric.state_dict().items()):
        tensor = tensor.detach().cpu().contiguous()
        state_hash.update(name.encode())
        state_hash.update(str(tensor.dtype).encode())
        state_hash.update(str(tuple(tensor.shape)).encode())
        state_hash.update(tensor.numpy().tobytes())
    provenance = {"pyiqa": version("pyiqa"), "torch": str(torch.__version__),
                  "python": platform.python_version(), "platform": platform.platform(),
                  "device": "cpu", "checkpoint_sha256": state_hash.hexdigest(),
                  "preprocessing": "pyiqa metric image-path input; pinned package defaults"}
    for previous in db.execute("SELECT config_json, provenance_json FROM scoring_run"):
        if json.loads(previous["config_json"]).get("experiment_name") == config["experiment_name"]:
            old = json.loads(previous["provenance_json"])
            if old != provenance:
                raise ValueError("Experiment scoring runtime/checkpoint changed; use the original environment or a new experiment name.")
    with db:
        cursor = db.execute("INSERT INTO scoring_run(generation_id,config_json,provenance_json) VALUES (?,?,?)", (generation_id,json.dumps(config,sort_keys=True),json.dumps(provenance,sort_keys=True)))
        run_id = cursor.lastrowid
        for frame in frames:
            path = ROOT / frame["image_path"]
            before = digest(path)
            with torch.inference_mode():
                score = float(metric(str(path)).item())
            if not math.isfinite(score) or digest(path) != before:
                raise ValueError("Invalid score or image changed during scoring.")
            db.execute("INSERT INTO image_score VALUES (?,?,?,?)", (run_id,frame["image_id"],before,score))
            db.execute("UPDATE image SET quality_score=? WHERE image_id=?", (score,frame["image_id"]))
        db.execute("UPDATE generation SET quality_model='musiq',quality_version=?,quality_threshold=? WHERE generation_id=?", (version("pyiqa"),config["quality_threshold"],generation_id))
    save_records(db)
    print("Scoring run:", run_id)
    return run_id


def select_pair(db, scoring_run_id):
    scoring = db.execute("SELECT * FROM scoring_run WHERE scoring_run_id=?", (scoring_run_id,)).fetchone()
    if scoring is None:
        raise ValueError("Scoring run not found.")
    config = json.loads(scoring["config_json"])
    frames = db.execute("SELECT image.*, image_score.score, image_score.sha256 FROM image_score JOIN image USING(image_id) WHERE scoring_run_id=? AND score>=? ORDER BY image_id", (scoring_run_id,config["quality_threshold"])).fetchall()
    for frame in frames:
        if digest(ROOT / frame["image_path"]) != frame["sha256"]:
            raise ValueError(f"Image {frame['image_id']} changed since scoring.")
        print(f"Image {frame['image_id']}: {ROOT / frame['image_path']} ({frame['score']:.2f})")
    with db:
        db.execute("INSERT OR IGNORE INTO review_run(generation_id,scoring_run_id) VALUES (?,?)", (scoring["generation_id"],scoring_run_id))
    completed = {(r[0],r[1]) for r in db.execute("SELECT image_id_1,image_id_2 FROM image_pairs WHERE scoring_run_id=?", (scoring_run_id,))}
    print(f"Candidate pairs: {len(frames)*(len(frames)-1)//2}; already reviewed: {len(completed)}")
    for first, second in itertools.combinations(frames, 2):
        ids = first["image_id"], second["image_id"]
        if ids in completed:
            continue
        print(f"Images {ids[0]} and {ids[1]}")
        answer = input("Same tattoo? [y/n]: ").strip().lower()
        if answer not in ("y", "n"):
            raise ValueError("Enter y or n. Completed reviews have been saved.")
        ratings = [None]*4
        total = None
        if answer == "y":
            ratings = [read_number(f"{k} [1-5]: ", integer=True) for k in CRITERIA]
            if any(v < 1 or v > 5 for v in ratings):
                raise ValueError("Ratings must be 1 through 5. Completed reviews have been saved.")
            weights = config["weights"]
            total = 100 * sum(weights[k]*v for k,v in zip(CRITERIA,ratings)) / (5*sum(weights.values()))
        with db:
            db.execute("INSERT INTO image_pairs(scoring_run_id,generation_id,image_id_1,image_id_2,same_tattoo,consistency,visibility,prompt_adherence,variation,total_score) VALUES (?,?,?,?,?,?,?,?,?,?)", (scoring_run_id,scoring["generation_id"],*ids,int(answer=="y"),*ratings,total))
        save_records(db)
    best = db.execute("SELECT * FROM image_pairs WHERE scoring_run_id=? AND same_tattoo=1 ORDER BY total_score DESC,image_id_1,image_id_2 LIMIT 1", (scoring_run_id,)).fetchone()
    with db:
        db.execute("UPDATE review_run SET status='complete',selected_pair_id=? WHERE scoring_run_id=?", (best["pair_id"] if best else None,scoring_run_id))
    save_records(db)
    print(f"Selected images {best['image_id_1']} and {best['image_id_2']}: {best['total_score']:.1f}" if best else "Review complete. No matching pair selected.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("register", "extract", "score", "review", "run"))
    parser.add_argument("--generation-id", type=int)
    parser.add_argument("--scoring-run-id", type=int)
    parser.add_argument("--config", type=Path, default=ROOT / "config/evaluation.json")
    args = parser.parse_args()
    db = connect()
    try:
        if args.command == "review":
            if args.scoring_run_id is None:
                raise ValueError("review requires --scoring-run-id")
            select_pair(db,args.scoring_run_id)
            return
        if args.command == "register":
            register_video(db)
            return
        config = load_config(args.config)
        freeze_config(db,config)
        gid = args.generation_id
        if gid is None:
            if args.command != "run":
                raise ValueError("This command requires --generation-id")
            gid, _, _ = register_video(db)
        row, video, method = generation_info(db,gid)
        has_frames = db.execute("SELECT 1 FROM image WHERE generation_id=?", (gid,)).fetchone()
        if args.command == "extract" and has_frames:
            raise ValueError("Frames already extracted; use score or review.")
        if args.command == "extract" or (args.command == "run" and not has_frames):
            extract_frames(db,gid,video,method,config["frame_interval"])
        if args.command in ("score", "run"):
            existing = db.execute("SELECT scoring_run_id FROM scoring_run WHERE generation_id=? AND config_json=? ORDER BY scoring_run_id DESC LIMIT 1", (gid,json.dumps(config,sort_keys=True))).fetchone()
            run_id = existing[0] if existing and args.command == "run" else score_frames(db,gid,config)
            if args.command == "run":
                select_pair(db,run_id)
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Cancelled. Completed stages and reviews remain saved.")
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as error:
        raise SystemExit(str(error))
