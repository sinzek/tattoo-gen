# Registers a manually generated video, extracts and scores frames with MUSIQ,
# filters frames by a quality threshold, and saves the highest-rated image pair
# based on manual scoring. Images stay in the baseline/proposed folders,
# and database records are saved to JSON for reloading.

import itertools
import json
import math
import shutil
import sqlite3
import uuid
from pathlib import Path

import cv2
import pyiqa
import torch

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


def extract_and_score(db, generation_id, video, method, interval, metric):
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

                    with torch.inference_mode():
                        score = float(metric(str(path)).item())
                    if not math.isfinite(score):
                        raise ValueError("Invalid quality score.")

                    db.execute(
                        """INSERT INTO image
                           (generation_id, frame_number, image_path, quality_score)
                           VALUES (?, ?, ?, ?)""",
                        (
                            generation_id, frame_number,
                            path.relative_to(ROOT).as_posix(), score,
                        ),
                    )
                    print(f"Frame {frame_number}: {score:.2f}")

                frame_number += 1

            expected = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            if frame_number == 0:
                raise ValueError("No frames could be read.")
            if math.isfinite(expected) and expected > frame_number + 1:
                raise ValueError("Video decoding stopped early.")

            from importlib.metadata import version
            db.execute(
                """UPDATE generation
                   SET quality_model = ?, quality_version = ?, frame_interval = ?
                   WHERE generation_id = ?""",
                ("musiq", version("pyiqa"), interval, generation_id),
            )

    except BaseException:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    finally:
        capture.release()

    save_records(db)
    print("Images saved in:", folder)


def select_pair(db, generation_id, threshold):
    frames = db.execute(
        """SELECT * FROM image
           WHERE generation_id = ? AND quality_score >= ?
           ORDER BY image_id""",
        (generation_id, threshold),
    ).fetchall()

    if len(frames) < 2:
        print("Fewer than two frames passed. No pair selected.")
        return

    print(f"\n{len(frames)} frames passed:")
    for frame in frames:
        print(
            f"Image {frame['image_id']}: {frame['image_path']} "
            f"(quality {frame['quality_score']:.2f})"
        )

    print("\nOpen these images in your image viewer.")
    print("Rate matching pairs from 1 (poor) to 5 (excellent).")
    print(f"Possible pairs: {len(frames) * (len(frames) - 1) // 2}")
    criteria = ("consistency", "visibility", "prompt_adherence", "variation")
    best = None

    for first, second in itertools.combinations(frames, 2):
        print(f"\nImages {first['image_id']} and {second['image_id']}")
        answer = input("Same tattoo? [y/n]: ").strip().lower()
        if answer not in ("y", "n"):
            raise ValueError("Enter y or n.")
        if answer == "n":
            continue

        ratings = [
            read_number(f"{name.replace('_', ' ')} [1-5]: ", integer=True)
            for name in criteria
        ]
        if any(score < 1 or score > 5 for score in ratings):
            raise ValueError("Ratings must be between 1 and 5.")

        total = sum(ratings) / 20 * 100
        if best is None or total > best["total"]:
            best = {
                "first": first["image_id"], "second": second["image_id"],
                "ratings": ratings, "total": total,
            }

    if best is None:
        print("No matching pair selected.")
        return

    with db:
        db.execute(
            """INSERT INTO image_pairs
               (generation_id, image_id_1, image_id_2, same_tattoo,
                consistency, visibility, prompt_adherence, variation, total_score)
               VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)""",
            (
                generation_id, best["first"], best["second"],
                *best["ratings"], best["total"],
            ),
        )
    save_records(db)
    print(
        f"\nSelected images {best['first']} and {best['second']}. "
        f"Pair score: {best['total']:.1f}"
    )


def main():
    db = connect()
    try:
        interval = read_number("Seconds between frames [1]: ", default=1)
        if interval <= 0:
            raise ValueError("Interval must be positive.")

        print("Loading MUSIQ. First use downloads pretrained weights.")
        metric = pyiqa.create_metric("musiq", device="cpu")
        metric.eval()

        generation_id, video, method = register_video(db)
        extract_and_score(
            db, generation_id, video, method, interval, metric
        )

        threshold = read_number("Minimum MUSIQ quality score: ")
        with db:
            db.execute(
                "UPDATE generation SET quality_threshold = ? WHERE generation_id = ?",
                (threshold, generation_id),
            )
        save_records(db)
        select_pair(db, generation_id, threshold)
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled. Previously committed records remain saved.")
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as error:
        raise SystemExit(str(error))