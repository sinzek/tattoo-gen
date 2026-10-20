# Run from the repository root: python src/create_database.py

import csv
import sqlite3
from pathlib import Path


ROOT_DIRECTORY = Path(__file__).resolve().parents[2]

DATABASE_PATH = ROOT_DIRECTORY / "SQLite" / "tattoo_gen.db"
SCHEMA_PATH = ROOT_DIRECTORY / "SQLite" / "schema.sql"
ALLOWED_VALUES_PATH = (
    ROOT_DIRECTORY / "SQLite" / "seed_allowed_values.sql"
)
PROMPTS_PATH = (
    ROOT_DIRECTORY / "data" / "metadata" / "model_selection_prompts.csv"
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


def load_prompts(connection, allowed_values):
    inserted_count = 0

    with open(PROMPTS_PATH, "r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        for row in reader:
            if not is_valid_row(row, allowed_values):
                continue

            subject_id = insert_subject(connection, row)
            tattoo_id = insert_tattoo(connection, row)
            scene_id = insert_scene(connection, row)

            insert_prompt(
                connection,
                row,
                subject_id,
                tattoo_id,
                scene_id,
            )

            inserted_count += 1

    return inserted_count


TABLES = ("subject", "tattoo", "scene", "prompt", "generation", "image", "image_pairs")
METADATA_PATH = ROOT_DIRECTORY / "data/metadata/database_records.json"


def connect():
    if not DATABASE_PATH.is_file():
        raise ValueError("Run python src/create_database.py first.")
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
        if not exists and table == "image_pairs":
            records[table] = []
            continue
        cursor = connection.execute(f"SELECT * FROM {table}")
        columns = [item[0] for item in cursor.description]
        records[table] = [dict(zip(columns,row)) for row in cursor.fetchall()]
    METADATA_PATH.parent.mkdir(parents=True,exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=METADATA_PATH.parent,suffix=".tmp")
    try:
        with os.fdopen(handle,"w",encoding="utf-8") as stream:
            json.dump({"format_version":1,"tables":records},stream,indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,METADATA_PATH)
    finally:
        Path(temporary).unlink(missing_ok=True)


def restore_records(connection):
    import json
    data=json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    if data.get("format_version") not in (1,2) or not isinstance(data.get("tables"),dict):
        raise ValueError("Invalid metadata file.")
    records=data["tables"]
    if not set(TABLES[:-1]).issubset(records):
        raise ValueError("Required metadata tables are missing.")
    # Also accepts snapshots from the earlier, larger implementation.
    for table in TABLES:
        allowed={row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        rows=records.get(table,[])
        if not isinstance(rows,list):
            raise ValueError(f"Invalid records for {table}.")
        for row in rows:
            if not isinstance(row,dict):
                raise ValueError(f"Invalid row for {table}.")
            values={key:value for key,value in row.items() if key in allowed}
            if not values:
                raise ValueError(f"Empty row for {table}.")
            columns=", ".join(values)
            placeholders=", ".join("?" for _ in values)
            connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",list(values.values()))


def create_database():
    import os
    import tempfile
    if DATABASE_PATH.exists():
        old = sqlite3.connect(DATABASE_PATH)
        try:
            save_records(old)
        finally:
            old.close()
    DATABASE_PATH.parent.mkdir(parents=True,exist_ok=True)
    handle, temporary=tempfile.mkstemp(dir=DATABASE_PATH.parent,suffix=".db")
    os.close(handle)
    connection=sqlite3.connect(temporary)
    try:
        execute_sql_file(connection,SCHEMA_PATH)
        execute_sql_file(connection,ALLOWED_VALUES_PATH)
        if METADATA_PATH.exists():
            restore_records(connection)
            print("Reloaded saved records.")
        else:
            print("Prompts inserted:",load_prompts(connection,load_allowed_values(connection)))
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign-key validation failed.")
        connection.commit()
        save_records(connection)
        connection.close()
        os.replace(temporary,DATABASE_PATH)
    finally:
        connection.close()
        Path(temporary).unlink(missing_ok=True)
    print("Database ready:",DATABASE_PATH)


if __name__=="__main__":
    import sys
    try:
        if sys.argv[1:]==["--export"]:
            connection=connect()
            try:
                save_records(connection)
                print("Saved:",METADATA_PATH)
            finally:
                connection.close()
        elif sys.argv[1:]:
            raise ValueError("Usage: python src/create_database.py [--export]")
        else:
            create_database()
    except (ValueError,OSError,sqlite3.Error) as error:
        raise SystemExit(str(error))
