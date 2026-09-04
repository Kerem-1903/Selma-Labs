# Akira V2 Identity Pipeline

Akira V1 is a preview model, not a production identity model. Its dataset passed
the former file-count check, but it was never approved image by image and its
Golden Set remains unlocked. Production generation must therefore treat V1 as
unverified.

## Why the previous scene failed

- Several compound camera views were captioned as generic front views.
- Hair-streak count and placement vary between source images.
- The model entered training without an approved canonical-anchor hash.
- No per-image identity, anatomy, and caption review was required.
- A character cutout placed over a background does not automatically inherit
  scene lighting, wetness, contact shadows, or edge color.

## V2 gates

1. Use the locked neutral identity anchor at
   `assets/characters/akira/identity_lock/v2/akira-canonical-anchor-v2.png`.
2. Keep its approved SHA-256 hash in the review manifest. The V2 anchor was
   human-approved on 2026-09-04 and must not be replaced without a new lock version.
3. Generate the 20 training and 3 holdout references through SELMA Labs.
4. Review every source image against the anchor. A sample passes only when:
   - identity score is at least `0.90`;
   - anatomy score is at least `0.85`;
   - its caption matches the visible view and pose;
   - a named reviewer approves it;
   - the reviewed source hash still matches the file.
5. Build a schema-v2 dataset. The build may complete while training remains
   blocked; these are deliberately separate states.
6. Train Akira V2 only after `training_approved=true`.
7. Run the ten-case Golden Set. No scene generation may call the model locked
   until all ten cases pass and a human locks the set.

## Commands

Build a reviewable dataset (this correctly exits with status 2 until all reviews
are supplied):

```powershell
python -m cli.main character dataset `
  --input assets/character_bibles/akira.json `
  --source output/training/akira-lora-v1-source `
  --output output/training/akira-lora-v2-curation `
  --trigger-token selma_akira_v2 `
  --canonical-anchor assets/characters/akira/identity_lock/v2/akira-canonical-anchor-v2.png
```

Audit any old or new dataset without starting GPU training:

```powershell
python -m cli.main character audit-dataset `
  --manifest output/training/akira-lora-v2-curation/manifest.json
```

Create the pending per-image review form automatically:

```powershell
python -m cli.main character review-template `
  --manifest output/training/akira-lora-v2-curation/manifest.json `
  --canonical-anchor assets/characters/akira/identity_lock/v2/akira-canonical-anchor-v2.png `
  --output output/training/akira-lora-v2-curation/review.json
```

After image review, rebuild with `--review-manifest <review.json>`. The review
file must use this shape for every source filename:

```json
{
  "schema_version": 1,
  "character_id": "akira",
  "approved_by": "reviewer-name",
  "canonical_anchor_sha256": "<64-character-sha256>",
  "reviews": {
    "face-closeup-front.png": {
      "identity_score": 0.95,
      "anatomy_score": 0.90,
      "caption_matches": true,
      "human_approved": true,
      "reviewer": "reviewer-name",
      "content_hash": "<reviewed-source-sha256>",
      "notes": "Matches the approved anchor."
    }
  }
}
```

## Scene integration order

Do not return to rain-scene compositing until V2 passes its Golden Set. Once it
does, generate the character and clean background separately, then use an anime
matting model for alpha, followed by contact shadow, scene-color relighting,
wet-surface highlights, rain occlusion in front of and behind the character, and
a final human shot approval. Generic person segmentation is preview-only and
must not be considered production matting.
