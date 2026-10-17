# Run this file from the repo root to create the tattoo_gen.db file via bash: python src/database/create_database.py

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


def create_database():
    connection = sqlite3.connect(DATABASE_PATH)

    # Enable foreign-key enforcement
    connection.execute("PRAGMA foreign_keys = ON")

    execute_sql_file(connection, SCHEMA_PATH)
    execute_sql_file(connection, ALLOWED_VALUES_PATH)

    allowed_values = load_allowed_values(connection)
    inserted_count = load_prompts(connection, allowed_values)

    connection.commit()
    connection.close()

    print(f"Prompts inserted: {inserted_count}")


if __name__ == "__main__":
    create_database()