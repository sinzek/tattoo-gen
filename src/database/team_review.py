"""Build an offline team review packet or record three completed reviews."""

import argparse
from contextlib import closing
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import sqlite3
from statistics import median
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from database.create_database import connect, save_records
from database.process_video import CRITERIA, ROOT, digest, freeze_config, load_config


TEAM_RULE = {"reviewers": 3, "identity_rule": "unanimous", "rating_rule": "median"}


def load_study(db, phase, source, config):
    if config.get("team_review") != TEAM_RULE:
        raise ValueError("This workflow requires three reviewers, unanimous identity and median ratings.")
    freeze_config(db, config)
    clips = {}
    pairs = {}
    for row in db.execute(
        """SELECT g.generation_id, g.prompt_id, p.prompt_text,
                  r.scoring_run_id, r.config_json, r.provenance_json
           FROM generation g JOIN prompt p USING (prompt_id)
           LEFT JOIN scoring_run r ON r.scoring_run_id = (
               SELECT MAX(scoring_run_id) FROM scoring_run
               WHERE generation_id = g.generation_id
                 AND json_extract(config_json, '$.experiment_name') = ?
           )
           WHERE g.video_path LIKE ? AND json_extract(g.settings_json, '$.prompt_set') = 'dataset'
           ORDER BY g.prompt_id, g.generation_id""",
        (source, f"data/videos/{phase}/%"),
    ):
        gid = row["generation_id"]
        if row["scoring_run_id"] is None:
            raise ValueError(f"Generation {gid} has no scores in {source}.")
        original = json.loads(row["config_json"])
        if any(original[key] != config[key] for key in ("metric", "device", "frame_interval")):
            raise ValueError(f"Generation {gid} was scored with different settings.")
        frames = [dict(frame) for frame in db.execute(
            """SELECT image_id, image_path, frame_number, score, sha256
               FROM image_score JOIN image USING (image_id)
               WHERE scoring_run_id=? AND generation_id=? ORDER BY image_id""",
            (row["scoring_run_id"], gid),
        )]
        if not frames:
            raise ValueError(f"Generation {gid} is missing scored frames.")
        for frame in frames:
            if digest(ROOT / frame["image_path"]) != frame["sha256"]:
                raise ValueError(f"Image {frame['image_id']} changed since scoring.")
        clips[gid] = {**dict(row), "frames": frames}
        passing = [f for f in frames if f["score"] >= config["quality_threshold"]]
        for first, second in combinations(passing, 2):
            pair_id = f"P{len(pairs) + 1:03d}"
            pairs[pair_id] = (gid, first, second)
    if not clips:
        raise ValueError(f"No scored dataset clips found for {phase}.")
    if len({clip["prompt_id"] for clip in clips.values()}) != len(clips):
        raise ValueError(f"Expected one generation per prompt in {phase}.")
    provenance = {clip["provenance_json"] for clip in clips.values()}
    provenance.update(row[0] for row in db.execute(
        "SELECT DISTINCT provenance_json FROM scoring_run WHERE config_json=?",
        (json.dumps(config, sort_keys=True),),
    ))
    if len(provenance) != 1:
        raise ValueError("MUSIQ provenance differs between study scoring runs.")
    study = json.dumps({"phase": phase, "config": config, "clips": clips}, sort_keys=True)
    return clips, pairs, sha256(study.encode()).hexdigest()


def build_packet(clips, pairs, packet_id, output):
    if not pairs:
        raise ValueError("No pairs pass the MUSIQ gate.")
    if output.exists():
        raise ValueError(f"Packet already exists: {output}")
    images = {}
    items = []
    for pair_id, (gid, first, second) in pairs.items():
        paths = []
        for frame in (first, second):
            name = images.setdefault(frame["image_path"], f"frames/{len(images) + 1:03d}.png")
            paths.append(name)
        items.append({"id": pair_id, "prompt": clips[gid]["prompt_text"], "images": paths})
    data = json.dumps({"id": packet_id, "items": items}).replace("<", "\\u003c")
    template = (ROOT / "docs/team-review.html").read_text(encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as work:
        staged = Path(work) / "packet.zip"
        with ZipFile(staged, "w", compression=ZIP_DEFLATED, compresslevel=3) as packet:
            packet.writestr("START.txt", "Unzip the entire folder and open Review.html in a browser.\n"
                            "Rate independently. Download your completed JSON and return it privately to the coordinator.\n")
            packet.writestr("Review.html", template.replace("__PACKET_DATA__", data))
            for path, name in images.items():
                packet.write(ROOT / path, name)
        staged.replace(output)
    print(f"{len(pairs)} pairs, {len(images)} original frames, {output}")


def complete_reviews(paths, pairs, packet_id):
    reviews = {}
    for path in paths:
        submission = json.loads(path.read_text(encoding="utf-8"))
        name = submission["reviewer"].strip()
        ratings = submission["ratings"]
        if not name or name.casefold() in reviews:
            raise ValueError("Each submission needs a distinct reviewer name.")
        if submission["packet"] != packet_id or set(ratings) != set(pairs):
            raise ValueError(f"{path.name} is incomplete or belongs to another packet.")
        for pair_id, judgment in ratings.items():
            identity = judgment.get("same_tattoo")
            notes = judgment.get("notes")
            scores = judgment.get("scores")
            if type(identity) is not bool or not isinstance(notes, str) or not isinstance(scores, dict):
                raise ValueError(f"{path.name}: invalid judgment on {pair_id}.")
            if identity:
                if set(scores) != set(CRITERIA) or any(type(v) is not int or not 1 <= v <= 5 for v in scores.values()):
                    raise ValueError(f"{path.name}: rate all four criteria on {pair_id}.")
            elif scores or not notes.strip():
                raise ValueError(f"{path.name}: a rejected pair needs an explanation on {pair_id}.")
        reviews[name.casefold()] = ratings
    return list(reviews.values())


def consolidate(db, clips, pairs, config, reviews):
    judgments = {gid: [] for gid in clips}
    weights = config["weights"]
    for pair_id, (gid, first, second) in pairs.items():
        votes = [review[pair_id] for review in reviews]
        yes = sum(vote["same_tattoo"] for vote in votes)
        ratings = [
            median(vote["scores"][key] for vote in votes) if yes == 3 else None
            for key in CRITERIA
        ]
        total = 20 * sum(weights[key] * v for key, v in zip(CRITERIA, ratings)) / sum(weights.values()) if yes == 3 else None
        judgments[gid].append({
            "pair": pair_id, "images": [first["image_id"], second["image_id"]],
            "yes_votes": yes, "ratings": ratings, "total": total,
            "notes": [vote["notes"] for vote in votes],
        })
    config_json = json.dumps(config, sort_keys=True)
    report = []
    with db:
        db.execute("BEGIN IMMEDIATE")
        freeze_config(db, config)
        for previous in db.execute("SELECT provenance_json FROM scoring_run WHERE config_json=?", (config_json,)):
            if previous[0] != next(iter(clips.values()))["provenance_json"]:
                raise ValueError("MUSIQ provenance differs from the other study runs.")
        for gid, clip in clips.items():
            if db.execute("SELECT 1 FROM scoring_run WHERE generation_id=? AND config_json=?", (gid, config_json)).fetchone():
                raise ValueError(f"Generation {gid} already has a run for {config['experiment_name']}.")
            run = db.execute(
                "INSERT INTO scoring_run(generation_id, config_json, provenance_json) VALUES (?,?,?)",
                (gid, config_json, clip["provenance_json"]),
            ).lastrowid
            db.execute(
                """INSERT INTO image_score SELECT ?, image_id, sha256, score
                   FROM image_score WHERE scoring_run_id=?""",
                (run, clip["scoring_run_id"]),
            )
            db.execute("INSERT INTO review_run(generation_id, scoring_run_id) VALUES (?,?)", (gid, run))
            for judgment in judgments[gid]:
                db.execute(
                    """INSERT INTO image_pairs(scoring_run_id, generation_id, image_id_1, image_id_2,
                       same_tattoo, consistency, visibility, prompt_adherence, variation, total_score)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (run, gid, *judgment["images"], int(judgment["yes_votes"] == 3),
                     *judgment["ratings"], judgment["total"]),
                )
            db.execute(
                """UPDATE review_run SET status='complete', selected_pair_id=(
                       SELECT pair_id FROM image_pairs WHERE scoring_run_id=? AND same_tattoo=1
                       ORDER BY total_score DESC, image_id_1, image_id_2 LIMIT 1
                   ) WHERE scoring_run_id=?""",
                (run, run),
            )
            eligible = [item for item in judgments[gid] if item["yes_votes"] == 3]
            winner = min(eligible, key=lambda item: (-item["total"], item["images"]), default=None)
            report.append({"generation_id": gid, "prompt_id": clip["prompt_id"], "winner": winner,
                           "frames": clip["frames"], "candidates": judgments[gid]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("packet", "collect"))
    parser.add_argument("--phase", choices=("baseline", "proposed"), default="baseline")
    parser.add_argument("--source", default="ltx2-baseline-raw-musiq")
    parser.add_argument("--config", type=Path, default=ROOT / "config/team-review.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, nargs=3)
    args = parser.parse_args()
    config = load_config(args.config)
    with closing(connect()) as db:
        clips, pairs, packet_id = load_study(db, args.phase, args.source, config)
        if args.command == "packet":
            build_packet(clips, pairs, packet_id, args.output)
            return
        if args.ratings is None:
            parser.error("collect requires three --ratings files")
        if args.output.exists():
            raise ValueError(f"Report already exists: {args.output}")
        reviews = complete_reviews(args.ratings, pairs, packet_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = consolidate(db, clips, pairs, config, reviews)
        save_records(db)
        args.output.write_text(json.dumps({"packet": packet_id, "clips": report}, indent=2) + "\n",
                               encoding="utf-8")
        count = sum(clip["winner"] is not None for clip in report)
        split = sum(0 < item["yes_votes"] < 3 for clip in report for item in clip["candidates"])
        print(f"Selected {count} pairs across {len(report)} scored clips. Identity votes split on {split} pairs.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError, AttributeError) as error:
        raise SystemExit(str(error))
