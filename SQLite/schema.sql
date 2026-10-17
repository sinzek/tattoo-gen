-- ======================== TATTOO GEN SCHEMA ========================

PRAGMA foreign_keys = ON;


-- ======================== DROP EXISTING TABLES ========================

-- Drop tables in dependency order
DROP TABLE IF EXISTS image;
DROP TABLE IF EXISTS generation;
DROP TABLE IF EXISTS prompt;
DROP TABLE IF EXISTS subject;
DROP TABLE IF EXISTS tattoo;
DROP TABLE IF EXISTS scene;
DROP TABLE IF EXISTS allowed_values;


-- ======================== TABLES ========================

-- For ease of prompt validation, we create an allowed_values table
-- containing all acceptable values for each controlled prompt field.
CREATE TABLE allowed_values (
    entity TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL,
    description TEXT NOT NULL,

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
    motif TEXT NOT NULL CHECK (length(trim(motif)) > 0),
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
-- and stores the exact text sent to the generation model
CREATE TABLE prompt (
    prompt_id INTEGER PRIMARY KEY,

    subject_id INTEGER NOT NULL,
    tattoo_id INTEGER NOT NULL,
    scene_id INTEGER NOT NULL,
    prompt_text TEXT NOT NULL CHECK (length(trim(prompt_text)) > 0),

    FOREIGN KEY (subject_id) REFERENCES subject(subject_id),
    FOREIGN KEY (tattoo_id) REFERENCES tattoo(tattoo_id),
    FOREIGN KEY (scene_id) REFERENCES scene(scene_id)
);


-- 5) GENERATION: Stores information about one text-to-video generation
CREATE TABLE generation (
    generation_id INTEGER PRIMARY KEY,

    prompt_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    generation_seed INTEGER NOT NULL,
    generation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    video_path TEXT NOT NULL UNIQUE,

    FOREIGN KEY (prompt_id) REFERENCES prompt(prompt_id)
    UNIQUE (prompt_id, model_name, model_version, generation_seed)
);


-- 6) IMAGE: Stores an extracted image/frame and its associated information
CREATE TABLE image (
    image_id INTEGER PRIMARY KEY,

    generation_id INTEGER NOT NULL,
    frame_number INTEGER NOT NULL,
    image_path TEXT NOT NULL UNIQUE,
    quality_score REAL NOT NULL,

    FOREIGN KEY (generation_id) REFERENCES generation(generation_id)
);