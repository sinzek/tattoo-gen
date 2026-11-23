-- ======================== TATTOO GEN SCHEMA ========================

PRAGMA foreign_keys = ON;


-- For ease of prompt validation, this table stores the acceptable values for
-- each Subject, Tattoo, or Scene attribute (a 'controlled vocabulary').
CREATE TABLE allowed_values (
    entity TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL,
    description TEXT,

    PRIMARY KEY (entity, attribute, value)
);


-- 1) SUBJECT: Describes the synthetic person requested in the prompt
CREATE TABLE subject (
    subject_id INTEGER PRIMARY KEY,

    gender_presentation TEXT NOT NULL,
    age_range TEXT NOT NULL,
    skin_tone TEXT NOT NULL,
    body_type TEXT NOT NULL,
    upper_clothing TEXT NOT NULL,
    lower_clothing TEXT NOT NULL
);


-- 2) TATTOO: Describes the tattoo requested in the prompt
CREATE TABLE tattoo (
    tattoo_id INTEGER PRIMARY KEY,

    body_location TEXT NOT NULL,
    style TEXT NOT NULL,
    motif TEXT NOT NULL,
    color_mode TEXT NOT NULL,
    size TEXT NOT NULL,
    tattoo_age TEXT NOT NULL
);


-- 3) SCENE: Describes how the person/tattoo should be depicted
CREATE TABLE scene (
    scene_id INTEGER PRIMARY KEY,

    pose TEXT NOT NULL,
    camera_distance TEXT NOT NULL,
    camera_angle TEXT NOT NULL,
    lighting TEXT NOT NULL,
    environment TEXT NOT NULL,
    occlusion TEXT NOT NULL,
    motion TEXT NOT NULL,
    focus TEXT NOT NULL,
    visibility TEXT NOT NULL
);


-- 4) PROMPT: Combines one subject, tattoo, and scene
-- Stores the exact text sent to the generation model.
CREATE TABLE prompt (
    prompt_id INTEGER PRIMARY KEY,

    subject_id INTEGER NOT NULL REFERENCES subject,
    tattoo_id INTEGER NOT NULL REFERENCES tattoo,
    scene_id INTEGER NOT NULL REFERENCES scene,
    prompt_text TEXT NOT NULL CHECK (length(trim(prompt_text)) > 0)
);


-- 5) GENERATION: Stores the text-to-video generation info
-- Seeds may be NULL when the generation service does not provide one.
-- Quality fields summarize the latest scoring run; historical scores are separate.
CREATE TABLE generation (
    generation_id INTEGER PRIMARY KEY,

    prompt_id INTEGER NOT NULL REFERENCES prompt,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    generation_seed INTEGER CHECK (generation_seed >= 0),
    generation_time TEXT DEFAULT CURRENT_TIMESTAMP,

    video_path TEXT,
    settings_json TEXT NOT NULL DEFAULT '{}',

    quality_model TEXT,
    quality_version TEXT,
    frame_interval REAL CHECK (frame_interval > 0),
    quality_threshold REAL
);


-- 6) IMAGE: Stores each extracted frame and its associated info
-- Each frame is unique within its generation; image paths are globally unique.
-- The composite key supports checking that reviewed images share a generation.
CREATE TABLE image (
    image_id INTEGER PRIMARY KEY,

    generation_id INTEGER NOT NULL REFERENCES generation,
    frame_number INTEGER NOT NULL CHECK (frame_number >= 0),
    image_path TEXT NOT NULL UNIQUE,
    quality_score REAL,

    UNIQUE (generation_id, frame_number),
    UNIQUE (image_id, generation_id)
);


-- 7) SCORING_RUN: Records the configuration and provenance for a scoring pass
-- config_json stores the threshold, interval, experiment name, and review weights.
-- provenance_json stores checkpoint hash, package versions, and runtime details.
CREATE TABLE scoring_run (
    scoring_run_id INTEGER PRIMARY KEY,

    generation_id INTEGER NOT NULL REFERENCES generation,
    config_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (scoring_run_id, generation_id)
);


-- 8) IMAGE_SCORE: Preserves each frame's score and file hash for a scoring run
-- The hash allows review to detect an image modified after scoring.
CREATE TABLE image_score (
    scoring_run_id INTEGER NOT NULL REFERENCES scoring_run,
    image_id INTEGER NOT NULL REFERENCES image,

    sha256 TEXT NOT NULL,
    score REAL NOT NULL,

    PRIMARY KEY (scoring_run_id, image_id)
);


-- 9) REVIEW_RUN: Tracks resumable pair review for one scoring run
-- Each scoring run is reviewed once, so its ID also identifies the review.
-- selected_pair_id remains NULL until a matching winner is selected.
-- image_pairs is defined below; snapshot restoration defers foreign-key checks.
CREATE TABLE review_run (
    scoring_run_id INTEGER PRIMARY KEY,

    generation_id INTEGER NOT NULL REFERENCES generation,
    status TEXT NOT NULL DEFAULT 'in_progress'
        CHECK (status IN ('in_progress', 'complete')),
    selected_pair_id INTEGER REFERENCES image_pairs,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (scoring_run_id, generation_id),

    FOREIGN KEY (scoring_run_id, generation_id)
        REFERENCES scoring_run(scoring_run_id, generation_id)
);


-- 10) IMAGE_PAIRS: Saves every completed pair review, including rejected matches
-- Ratings are 1-5; the weighted total ranges from 20-100 for matching pairs.
-- Ordered image IDs prevent duplicate reversed pairs within a review run.
-- scoring_run_id may be NULL for legacy reviews without a recorded scoring run.
CREATE TABLE image_pairs (
    pair_id INTEGER PRIMARY KEY,

    scoring_run_id INTEGER,
    generation_id INTEGER NOT NULL REFERENCES generation,
    image_id_1 INTEGER NOT NULL,
    image_id_2 INTEGER NOT NULL,
    same_tattoo INTEGER NOT NULL CHECK (same_tattoo IN (0, 1)),

    consistency INTEGER CHECK (consistency BETWEEN 1 AND 5),
    visibility INTEGER CHECK (visibility BETWEEN 1 AND 5),
    prompt_adherence INTEGER CHECK (prompt_adherence BETWEEN 1 AND 5),
    variation INTEGER CHECK (variation BETWEEN 1 AND 5),
    total_score REAL CHECK (total_score BETWEEN 20 AND 100),

    CHECK (image_id_1 < image_id_2),
    CHECK (
        same_tattoo = 0 OR (
            consistency IS NOT NULL AND
            visibility IS NOT NULL AND
            prompt_adherence IS NOT NULL AND
            variation IS NOT NULL AND
            total_score IS NOT NULL
        )
    ),

    UNIQUE (scoring_run_id, image_id_1, image_id_2),

    FOREIGN KEY (scoring_run_id, generation_id)
        REFERENCES review_run(scoring_run_id, generation_id),
    FOREIGN KEY (image_id_1, generation_id)
        REFERENCES image(image_id, generation_id),
    FOREIGN KEY (image_id_2, generation_id)
        REFERENCES image(image_id, generation_id)
);


-- ======================== LOOKUP INDEXES ========================

CREATE INDEX image_generation_idx ON image(generation_id);
CREATE INDEX generation_prompt_idx ON generation(prompt_id);


-- ======================== SCHEMA VERSION ========================

PRAGMA user_version = 2;
