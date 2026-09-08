-- ====================== SEED FILE FOR ALLOWED VALUES ======================

-- The 'description' field provides context for the LLM when generating prompts, but isn't used for any validation purposes
-- The 'value' field is the only one used for validation, and will be stored in the prompt table for each field

-- ====================== SUBJECT VALUES ======================
-- == gender_presentation ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Subject', 'gender_presentation', 'masculine', 'Masculine-presenting subject'),
    ('Subject', 'gender_presentation', 'feminine', 'Feminine-presenting subject'),
    ('Subject', 'gender_presentation', 'androgynous', 'Androgynous-presenting subject');

-- == age_range ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Subject', 'age_range', '18-29', 'Young adult'),
    ('Subject', 'age_range', '30-39', 'Adult'),
    ('Subject', 'age_range', '40-49', 'Adult'),
    ('Subject', 'age_range', '50-59', 'Older adult'),
    ('Subject', 'age_range', '60+', 'Senior adult');

-- == skin_tone ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Subject', 'skin_tone', 'very_light', 'Very light skin tone'),


-- == body_type ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Subject', 'body_type', 'slim', 'Slim body type'),


-- ====================== TATTOO VALUES ======================
-- == body_location ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Tattoo', 'body_location', 'upper_arm', 'Upper arm tattoo location'),


-- == style==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Tattoo', 'style', 'traditional', 'Traditional tattoo style'),

-- == Motif ==
-- Motif can have hundreds of values, so we wont be seeding its allowed values here; instead, we'll simply validate that the motif is a non-empty string

-- == color_mode ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Tattoo', 'color_mode', 'color', 'Uses colored ink'),
    ('Tattoo', 'color_mode', 'monochrome', 'Uses black and gray ink');

-- == size ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Tattoo', 'size', 'small', 'Small tattoo size'),
    ('Tattoo', 'size', 'medium', 'Medium tattoo size'),
    ('Tattoo', 'size', 'large', 'Large tattoo size');

-- 