<<<<<<< Updated upstream
# tattoo-gen
COSC 4394 - Physical Computing for Image Analytics
=======
# Synthetic Tattoo Generation
  University of Houston - Computational Biomedicine Lab
  Research Project for Synthetic Tattoo Image Generation for Tattoo Recognition

# Project Overview 
This project will investigate the usage of text-to-video generation models to create synthetic tattoo images that can be used to develop and train tattoo-recognition systems.

Our approach will explore whether or not using text-to-video generation can produce a consistent amount of frames depicting the same synthetic individual and too; to find the most suitable frames that can be organized and selected into image pairs for use in tattoo-recognition research.

The project will also compare 
1) A baseline text-to-video generation method
  VS
2) A modified generation method

## Setup

Use a dedicated Python 3.11/3.12 environment. From the repository root:

```bash
python -m pip install -r requirements.txt
python src/create_database.py
python src/process_video.py
```

PyTorch dependencies can be large. For a CPU-only Windows/Linux install, first run:

```bash
python -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
```

Then install requirements.txt. Headless OpenCV is intentional: images are reviewed in a browser gallery. First MUSIQ use downloads pretrained weights. Scoring runs on CPU and can take time. No model training occurs.

# Project Pipeline

## Phase 0: Setting up our Tools 
- [ ] Create our detailed working github repository
- [ ] Organize repository folder structure
- [ ] 
- [ ]
- [ ]

## Phase 1: Dataset requirements 
- [ ] Discuss various project requirements among group members
- [ ] Evaluate our requirements for the tattoo recognition training
- [ ] Define the various requirements for subject/tattoo/person imagery
- [ ] Document our dataset requirements

## Phase _: Prompt Dataset

## Phase _: Literature Review: Text-to-Video

## Phase _: Literature Review: Image Quality
>>>>>>> Stashed changes
