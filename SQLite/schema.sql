-- ======================== TATTOO GEN SCHEMA ========================

CREATE DATABASE tattoo_gen;
USE tattoo_gen;

PRAGMA foreign_keys = ON;

-- Dropping existing tables in dependency order
DROP TABLE IF EXISTS allowed_values;
DROP TABLE IF EXISTS prompt;
DROP TABLE IF EXISTS subject;
DROP TABLE IF EXISTS tattoo;
DROP TABLE IF EXISTS scene;


-- For ease of prompt validation, we create an allowed_values table containing all of the acceptable values for each prompt field (a 'controlled vocabulary')
CREATE TABLE allowed_values (
    entity TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL,
    description TEXT,

    PRIMARY KEY (entity, attribute, value)
);

-- 1) PROMPT: Combines one subject, tattoo, and scene | Stores the exact text sent to the generation model
CREATE TABLE prompt (
    prompt_id INTEGER PRIMARY KEY,

    subject_id INTEGER NOT NULL,
    tattoo_id INTEGER NOT NULL,
    scene_id INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,

    FOREIGN KEY (subject_id) REFERENCES subject(subject_id),
    FOREIGN KEY (tattoo_id) REFERENCES tattoo(tattoo_id),
    FOREIGN KEY (scene_id) REFERENCES scene(scene_id)
);

-- 2) SUBJECT: Describes the synthetic person requested in the prompt
CREATE TABLE subject (
    subject_id INTEGER PRIMARY KEY,

    gender_presentation TEXT,
    age_range TEXT,
    skin_tone TEXT,
    body_type TEXT
);

-- 3) TATTOO: Describes the tattoo requested in the prompt
CREATE TABLE tattoo (
    tattoo_id INTEGER PRIMARY KEY,

    body_location TEXT,
    style TEXT,
    motif TEXT,
    color_mode TEXT,
    size TEXT,
    tattoo_age TEXT
);

-- 4) SCENE: Describes how the person/tattoo should be depicted
CREATE TABLE scene (
    scene_id INTEGER PRIMARY KEY,

    pose TEXT,
    camera_distance TEXT,
    camera_angle TEXT,
    lighting TEXT,
    environment TEXT,
    occlusion TEXT,
    motion TEXT,
    focus TEXT,
    visibility TEXT
);

-- 5) IMAGE: Stores the generated image file path and its associated info
CREATE TABLE image (
    image_id INTEGER PRIMARY KEY,

    generation_id INTEGER NOT NULL,
    frame_number INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    quality_score REAL,

    FOREIGN KEY (generation_id) REFERENCES generation(generation_id)
);


-- 6) GENERATION: Stores the text-to-video generation info
CREATE TABLE generation (
    generation_id INTEGER PRIMARY KEY,

    prompt_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    generation_seed INTEGER NOT NULL,
    generation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
);
