-- ====================== SEED FILE FOR ALLOWED VALUES ======================

-- The 'description' field provides context for the LLM when generating prompts, but isn't used for any validation purposes

-- The 'value' field is used for validation and represents an acceptable value for the corresponding Subject, Tattoo, or Scene attribute.
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
    ('Subject', 'skin_tone', 'light', 'Light skin tone'),
    ('Subject', 'skin_tone', 'medium', 'Medium skin tone'),
    ('Subject', 'skin_tone', 'tan', 'Tan skin tone'),
    ('Subject', 'skin_tone', 'dark', 'Dark skin tone'),
    ('Subject', 'skin_tone', 'very_dark', 'Very dark skin tone');

-- == body_type ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Subject', 'body_type', 'slim', 'Slim body type'),
    ('Subject', 'body_type', 'average', 'Average body type'),
    ('Subject', 'body_type', 'athletic', 'Athletic body type'),
    ('Subject', 'body_type', 'large', 'Large body type');

-- == upper_clothing ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Subject', 'upper_clothing', 'tank_top', 'Sleeveless top exposing the shoulders and arms'),
    ('Subject', 'upper_clothing', 'short_sleeve', 'Short-sleeved shirt covering the torso and upper portion of the arms'),
    ('Subject', 'upper_clothing', 'long_sleeve', 'Long-sleeved shirt covering the torso and arms');


-- == lower_clothing ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Subject', 'lower_clothing', 'shorts', 'Shorts exposing most of the lower legs'),
    ('Subject', 'lower_clothing', 'pants', 'Long pants covering the legs');


-- ====================== TATTOO VALUES ======================
-- == body_location ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Tattoo', 'body_location', 'upper_arm', 'Tattoo located on the upper arm'),
    ('Tattoo', 'body_location', 'forearm', 'Tattoo located on the forearm'),
    ('Tattoo', 'body_location', 'shoulder', 'Tattoo located on the shoulder'),
    ('Tattoo', 'body_location', 'chest', 'Tattoo located on the chest'),
    ('Tattoo', 'body_location', 'back', 'Tattoo located on the back'),
    ('Tattoo', 'body_location', 'thigh', 'Tattoo located on the thigh'),
    ('Tattoo', 'body_location', 'calf', 'Tattoo located on the calf');

-- == style==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Tattoo', 'style', 'traditional', 'Traditional tattoo style with bold outlines and simplified forms'),
    ('Tattoo', 'style', 'realism', 'Realistic tattoo style intended to resemble real subjects or objects'),
    ('Tattoo', 'style', 'geometric', 'Tattoo composed primarily of geometric shapes and patterns'),
    ('Tattoo', 'style', 'linework', 'Tattoo composed primarily of lines with limited shading'),
    ('Tattoo', 'style', 'blackwork', 'Tattoo using large areas of solid black ink'),
    ('Tattoo', 'style', 'watercolor', 'Tattoo using blended colors and watercolor-like visual effects');

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
    ('Tattoo', 'size', 'small', 'Small tattoo occupying a limited area of the selected body location'),
    ('Tattoo', 'size', 'medium', 'Medium tattoo occupying a moderate area of the selected body location'),
    ('Tattoo', 'size', 'large', 'Large tattoo occupying a substantial area of the selected body location');

-- == tattoo_age ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Tattoo', 'tattoo_age', 'fresh', 'Recently applied tattoo with a fresh appearance'),
    ('Tattoo', 'tattoo_age', 'healed', 'Fully healed tattoo with little visible aging'),
    ('Tattoo', 'tattoo_age', 'aged', 'Older tattoo showing visible fading or aging');


-- ====================== SCENE VALUES ======================

-- == pose ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Scene', 'pose', 'standing', 'Subject is standing'),
    ('Scene', 'pose', 'sitting', 'Subject is sitting'),
    ('Scene', 'pose', 'walking', 'Subject is walking');


-- == camera_distance ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Scene', 'camera_distance', 'close_up', 'Close view where the tattoo occupies a large portion of the frame'),
    ('Scene', 'camera_distance', 'medium', 'Medium-distance view showing the tattoo and surrounding body area'),
    ('Scene', 'camera_distance', 'full_body', 'Wide view showing most or all of the subject');


-- == camera_angle ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Scene', 'camera_angle', 'front', 'Camera views the subject from the front'),
    ('Scene', 'camera_angle', 'side', 'Camera views the subject from the side'),
    ('Scene', 'camera_angle', 'oblique', 'Camera views the subject from an angled perspective'),
    ('Scene', 'camera_angle', 'back', 'Camera views the subject from behind');


-- == lighting ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Scene', 'lighting', 'bright', 'Bright and evenly illuminated scene'),
    ('Scene', 'lighting', 'normal', 'Moderately and naturally illuminated scene'),
    ('Scene', 'lighting', 'dim', 'Low-light scene with reduced illumination');


-- == environment ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Scene', 'environment', 'studio', 'Controlled studio environment with a simple background'),
    ('Scene', 'environment', 'indoor', 'General indoor environment'),
    ('Scene', 'environment', 'outdoor', 'General outdoor environment');


-- == occlusion ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Scene', 'occlusion', 'none', 'Tattoo is not obstructed by another object'),
    ('Scene', 'occlusion', 'partial', 'A portion of the tattoo is obstructed while the tattoo remains identifiable');


-- == motion ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Scene', 'motion', 'stationary', 'Subject remains mostly stationary during the video'),
    ('Scene', 'motion', 'body_rotation', 'Subject gradually rotates their body during the video'),
    ('Scene', 'motion', 'limb_movement', 'Subject moves the tattooed limb during the video'),
    ('Scene', 'motion', 'walking', 'Subject walks naturally during the video');


-- == focus ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Scene', 'focus', 'tattoo', 'Camera focus is primarily on the tattoo'),
    ('Scene', 'focus', 'subject', 'Camera focus is primarily on the overall subject');


-- == visibility ==
INSERT INTO allowed_values
    (entity, attribute, value, description)
VALUES
    ('Scene', 'visibility', 'full', 'Entire tattoo is visible within the frame'),
    ('Scene', 'visibility', 'partial', 'Only part of the tattoo is visible within the frame');