# Run from the repository root: python -m database.create_database

import csv
from contextlib import closing
import sqlite3
from pathlib import Path


ROOT_DIRECTORY = Path(__file__).resolve().parents[2]

DATABASE_PATH = ROOT_DIRECTORY / "SQLite" / "tattoo_gen.db"
SCHEMA_PATH = ROOT_DIRECTORY / "SQLite" / "schema.sql"
ALLOWED_VALUES_PATH = (
    ROOT_DIRECTORY / "SQLite" / "seed_allowed_values.sql"
)
PROMPTS_PATH = (
    ROOT_DIRECTORY / "data" / "metadata" / "prompts.csv"
)

# Fields validated using the allowed_values table
CONTROLLED_FIELDS = {
    "Subject": [
        "gender_presentation",
        "age_range",
        "skin_tone",
        "body_type",
        "upper_clothing",
        "lower_clothing",
    ],
    "Tattoo": [
        "body_location",
        "style",
        "color_mode",
        "size",
        "tattoo_age",
    ],
    "Scene": [
        "pose",
        "camera_distance",
        "camera_angle",
        "lighting",
        "environment",
        "occlusion",
        "motion",
        "focus",
        "visibility",
    ],
}


def execute_sql_file(connection, file_path):
    with open(file_path, "r", encoding="utf-8") as sql_file:
        connection.executescript(sql_file.read())


def load_allowed_values(connection):
    rows = connection.execute(
        """
        SELECT entity, attribute, value
        FROM allowed_values
        """
    ).fetchall()

    allowed_values = {}

    for entity, attribute, value in rows:
        key = (entity, attribute)

        if key not in allowed_values:
            allowed_values[key] = set()

        allowed_values[key].add(value)

    return allowed_values


def is_valid_row(row, allowed_values):
    # Validate controlled fields
    for entity, attributes in CONTROLLED_FIELDS.items():
        for attribute in attributes:
            key = (entity, attribute)
            value = row[attribute].strip()

            if value not in allowed_values.get(key, set()):
                return False

    # Motif and prompt text must not be empty
    if not row["motif"].strip():
        return False

    if not row["prompt_text"].strip():
        return False

    return True


def insert_subject(connection, row):
    cursor = connection.execute(
        """
        INSERT INTO subject (
            gender_presentation,
            age_range,
            skin_tone,
            body_type,
            upper_clothing,
            lower_clothing
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            row["gender_presentation"].strip(),
            row["age_range"].strip(),
            row["skin_tone"].strip(),
            row["body_type"].strip(),
            row["upper_clothing"].strip(),
            row["lower_clothing"].strip(),
        ),
    )

    return cursor.lastrowid


def insert_tattoo(connection, row):
    cursor = connection.execute(
        """
        INSERT INTO tattoo (
            body_location,
            style,
            motif,
            color_mode,
            size,
            tattoo_age
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            row["body_location"].strip(),
            row["style"].strip(),
            row["motif"].strip(),
            row["color_mode"].strip(),
            row["size"].strip(),
            row["tattoo_age"].strip(),
        ),
    )

    return cursor.lastrowid


def insert_scene(connection, row):
    cursor = connection.execute(
        """
        INSERT INTO scene (
            pose,
            camera_distance,
            camera_angle,
            lighting,
            environment,
            occlusion,
            motion,
            focus,
            visibility
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["pose"].strip(),
            row["camera_distance"].strip(),
            row["camera_angle"].strip(),
            row["lighting"].strip(),
            row["environment"].strip(),
            row["occlusion"].strip(),
            row["motion"].strip(),
            row["focus"].strip(),
            row["visibility"].strip(),
        ),
    )

    return cursor.lastrowid


def insert_prompt(
    connection,
    row,
    subject_id,
    tattoo_id,
    scene_id,
):
    connection.execute(
        """
        INSERT INTO prompt (
            prompt_id,
            subject_id,
            tattoo_id,
            scene_id,
            prompt_text
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(row["prompt_id"]),
            subject_id,
            tattoo_id,
            scene_id,
            row["prompt_text"].strip(),
        ),
    )


def load_prompts(connection, allowed_values, path=None, id_offset=0):
    required = {"prompt_id", "motif", "prompt_text"}
    required.update(k for fields in CONTROLLED_FIELDS.values() for k in fields)
    with open(path or PROMPTS_PATH, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing headers: {sorted(missing)}")
        rows = list(reader)
    seen = set()
    for line, row in enumerate(rows, 2):
        if None in row or any(row.get(k) is None for k in required):
            raise ValueError(f"CSV row {line}: incorrect column count.")
        try:
            pid = int(row["prompt_id"])
        except ValueError:
            raise ValueError(f"CSV row {line}: noninteger prompt_id.") from None
        if pid <= 0 or pid in seen:
            raise ValueError(f"CSV row {line}: prompt_id must be positive and unique.")
        seen.add(pid)
        if not is_valid_row(row, allowed_values):
            invalid = [k for entity, fields in CONTROLLED_FIELDS.items() for k in fields if row[k].strip() not in allowed_values.get((entity,k),set())]
            invalid += [k for k in ("motif", "prompt_text") if not row[k].strip()]
            raise ValueError(f"CSV row {line}: invalid fields {invalid}")
        row["prompt_id"] = pid + id_offset
    with connection:
        for row in rows:
            pid = int(row["prompt_id"])
            existing = connection.execute("SELECT * FROM prompt WHERE prompt_id=?", (pid,)).fetchone()
            if existing:
                if connection.execute("SELECT 1 FROM generation WHERE prompt_id=?", (pid,)).fetchone():
                    # Never change the meaning of a prompt already used for generation.
                    for table, fields in CONTROLLED_FIELDS.items():
                        name = table.lower()
                        old = connection.execute(f"SELECT * FROM {name} WHERE {name}_id=?", (existing[f"{name}_id"],)).fetchone()
                        if any(old[k] != row[k].strip() for k in fields):
                            raise ValueError(f"Prompt {pid} has generations and changed attributes.")
                        if name == "tattoo" and old["motif"] != row["motif"].strip():
                            raise ValueError(f"Prompt {pid} has generations and a changed motif.")
                    if existing["prompt_text"] != row["prompt_text"].strip():
                        raise ValueError(f"Prompt {pid} has generations and changed text.")
                    continue
                connection.execute("DELETE FROM prompt WHERE prompt_id=?", (pid,))
            insert_prompt(connection, row, insert_subject(connection,row), insert_tattoo(connection,row), insert_scene(connection,row))
            if existing:
                for table in ("subject", "tattoo", "scene"):
                    key = f"{table}_id"
                    connection.execute(f"DELETE FROM {table} WHERE {key}=? AND NOT EXISTS (SELECT 1 FROM prompt WHERE {key}=?)", (existing[key], existing[key]))
    return len(rows)


TABLES = ("subject", "tattoo", "scene", "prompt", "generation", "image", "scoring_run", "image_score", "review_run", "image_pairs")
METADATA_PATH = ROOT_DIRECTORY / "data/metadata/database_records.json"


def connect():
    if not DATABASE_PATH.is_file():
        raise ValueError("Run python -m database.create_database first.")
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def save_records(connection):
    import json
    import os
    import tempfile
    records = {}
    for table in TABLES:
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            records[table] = []
            continue
        cursor = connection.execute(f"SELECT * FROM {table}")
        columns = [item[0] for item in cursor.description]
        records[table] = [dict(zip(columns,row)) for row in cursor.fetchall()]
    METADATA_PATH.parent.mkdir(parents=True,exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=METADATA_PATH.parent,suffix=".tmp")
    try:
        with os.fdopen(handle,"w",encoding="utf-8") as stream:
            json.dump({"format_version":4,"tables":records},stream,indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,METADATA_PATH)
    finally:
        Path(temporary).unlink(missing_ok=True)


def restore_records(connection):
    import json
    data=json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    if data.get("format_version") not in (1,2,3,4) or not isinstance(data.get("tables"),dict):
        raise ValueError("Invalid metadata file.")
    records=data["tables"]
    if not set(TABLES[:6]).issubset(records):
        raise ValueError("Required metadata tables are missing.")
    # Older snapshots linked pairs through a separate review ID. Map by value:
    # review IDs and scoring IDs are not necessarily equal.
    legacy_reviews = {
        row["review_run_id"]: row["scoring_run_id"]
        for row in records.get("review_run", [])
        if isinstance(row, dict) and "review_run_id" in row
    }
    if not connection.in_transaction:
        connection.execute("BEGIN")
    connection.execute("PRAGMA defer_foreign_keys=ON")
    # Also accepts snapshots from the earlier, larger implementation.
    for table in TABLES:
        allowed={row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        rows=records.get(table,[])
        if not isinstance(rows,list):
            raise ValueError(f"Invalid records for {table}.")
        for row in rows:
            if not isinstance(row,dict):
                raise ValueError(f"Invalid row for {table}.")
            row = dict(row)
            if table == "image_pairs" and "review_run_id" in row:
                legacy_id = row.pop("review_run_id")
                if legacy_id is not None:
                    if legacy_id not in legacy_reviews:
                        raise ValueError(f"Missing legacy review {legacy_id}.")
                    row["scoring_run_id"] = legacy_reviews[legacy_id]
            if table == "image" and "file_path" in row:
                row["image_path"] = row.pop("file_path")
            if table == "image_pairs" and "image_pair_id" in row:
                row["pair_id"] = row.pop("image_pair_id")
            values={key:value for key,value in row.items() if key in allowed}
            if not values:
                raise ValueError(f"Empty row for {table}.")
            columns=", ".join(values)
            placeholders=", ".join("?" for _ in values)
            connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",list(values.values()))


def create_database(mode="init"):
    import os
    import tempfile
    if mode in ("init", "restore") and DATABASE_PATH.exists():
        raise ValueError("Database exists. Use migrate or import-prompts.")
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=DATABASE_PATH.parent, suffix=".db")
    os.close(handle)
    connection = sqlite3.connect(temporary)
    connection.row_factory = sqlite3.Row
    try:
        execute_sql_file(connection, SCHEMA_PATH)
        execute_sql_file(connection, ALLOWED_VALUES_PATH)
        if mode == "migrate":
            if not DATABASE_PATH.exists():
                raise ValueError("No database to migrate.")
            backup = DATABASE_PATH.with_suffix(".db.bak")
            if backup.exists():
                raise ValueError(f"Backup already exists: {backup}")
            with closing(sqlite3.connect(DATABASE_PATH)) as old:
                with closing(sqlite3.connect(backup)) as target:
                    old.backup(target)
                save_records(old)
            restore_records(connection)
        elif mode == "restore":
            restore_records(connection)
        else:
            print("Prompts imported:", load_prompts(connection, load_allowed_values(connection)))
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign-key validation failed.")
        connection.commit()
        connection.close()
        os.replace(temporary, DATABASE_PATH)
    finally:
        connection.close()
        Path(temporary).unlink(missing_ok=True)
    db = connect()
    try:
        save_records(db)
    finally:
        db.close()
    print("Database ready:", DATABASE_PATH)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("init", "migrate", "restore", "import-prompts", "export"), default="init", nargs="?")
    args = parser.parse_args()
    if args.command in ("init", "migrate", "restore"):
        create_database(args.command)
    else:
        db = connect()
        try:
            if args.command == "import-prompts":
                print("Prompts imported:", load_prompts(db, load_allowed_values(db)))
            save_records(db)
        finally:
            db.close()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, sqlite3.Error) as error:
        raise SystemExit(str(error))
