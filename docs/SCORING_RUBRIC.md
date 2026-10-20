# Pair review rubric v1

These are subjective ratings, not automated identity verification. Use the same reviewer(s), criteria and fixed weights for baseline and revised prompts. Initial weights are equal; agree on the rubric before evaluating held-out outputs. Manual judgments and the learned quality model can introduce bias.

## Automatic gate

MUSIQ predicts whole-frame perceptual image quality without a reference image. Higher scores pass when score >= quality_threshold. This is not a probability, tattoo-fidelity score or training loss. It may favor a clear background over a distorted tattoo. No automatic tattoo cropping or matching is implemented.

Score a representative development/pilot sample first. Inspect pilot images against scores, choose one cutoff in config/evaluation.json, document the rationale and freeze it across compared methods. The shipped threshold is null intentionally; selection cannot start until you set a finite numeric threshold. Do not tune the cutoff separately for each video or method. Keep pilot videos separate from final evaluation videos. Below-threshold frames stay on disk for audit but cannot be reviewed or selected in that selection run.

## Pair labels and ratings

First label whether both images show the same tattoo (yes/no). If not, the pair cannot win regardless of its total. When uncertain, label no and note the uncertainty. A shared generation ID does not prove identical tattoos.

Rate each criterion 1 through 5:

| Criterion | 1 | 3 | 5 |
|---|---|---|---|
| Consistency | Major changes in tattoo design/location | Minor distortions; identity mostly retained | Same design and placement, accounting for perspective |
| Visibility | Tattoo obscured, tiny or uninspectable in either frame | Partly visible or moderately unclear | Clear and inspectable in both frames |
| Prompt adherence | Major requested subject/tattoo/scene attributes missing | Several attributes match; some mismatches | Requested attributes match in both frames |
| Variation | Near-identical/redundant views | Some useful pose/viewpoint/lighting difference | Substantial useful variation while retaining inspectable tattoo |

2 and 4 are intermediate judgments. Evaluate visibility using the weaker frame. Genuine differences in tattoos are inconsistency, not useful variation. If two frames are too similar because a prompt requested a stationary shot, rate variation honestly and note the reason.

Total = 100 * sum(weight * rating) / (5 * sum(weights)). The possible range is 20–100, not 0–100. A total is a rubric score, not an objectively calibrated quality value. Each selection run saves the exact threshold and config, so later config edits do not change past runs. Ties use lowest image IDs for repeatability. All eligible candidate pairs must be reviewed; otherwise selection remains in progress. There is no hidden top-k truncation. N passing frames give N*(N-1)/2 pairs: choose an appropriate extraction interval before the experiment.

## Provenance

Each immutable scoring run records pyiqa version, a SHA-256 digest of the loaded model state, runtime/device details, image hashes and scores. image.quality_score is the latest score for convenience; selection always uses an explicit scoring run. Scores are comparable only when using the same metric, weights/checkpoint and preprocessing. First use downloads weights. Review rejects missing or modified images. Selected frames are copies, preserving original data.

Sources:
- https://github.com/chaofengc/IQA-PyTorch (documented create_metric and inference API)
- https://github.com/chaofengc/IQA-PyTorch/blob/main/docs/ModelCard.md (MUSIQ higher-is-better)
- https://github.com/google-research/google-research/tree/master/musiq
