# Character Studio — No-LoRA production path

SELMA has one supported character-production path. Legacy 20+3 packs,
hand-maintained identity-lock folders and experiment outputs are not production
inputs.

## Directory ownership

```text
assets/
  character_creation_briefs/   # Human-authored visual design contracts
    akira.json
    kaito.json
  character_bibles/            # Story/canon identity; no generated images
    akira.json
  preproduction/                # Locked world, style and creative direction

output/                         # Runtime data; ignored by Git
  production/
    characters/<id>/vN/
      canonical_source.png
      canonical-approval.json
      anchors/
        face_anchor.png
        fullbody_anchor.png
      views/
      quarantine/
      contact-sheets/views.png
      view-pack.json
      view-pack-approval.json
      manifest.json
```

Generated character images never belong in `assets/character_bibles` or beside
workflow templates. A Character Bible may receive its runtime reference pack
only from a hash-verified, human-approved seven-view pack.

## Supported flow

1. Create design candidates from a confirmed brief. Candidate QC rejects
   collages, multiple people and cropped figures before they reach review.
2. A human selects exactly one candidate. Approval creates a locked canonical
   source plus face and full-body anchors.
3. Generate the seven canonical views through the staged reference chain.
   Failed attempts go to quarantine and are never eligible references.
4. Review the contact sheet and approve the complete pack.
5. Keyframe generation verifies `view-pack-approval.json` and all image hashes,
   then loads those seven views into the Character Bible at runtime.

Animation/keyframe production fails closed when any approval, view, hash or QC
record is absent.

## Commands

```powershell
python -m cli.main character create `
  --brief assets/character_creation_briefs/kaito.json `
  --run-id kaito-review-001 `
  --manifest output/production/review/kaito-design-candidates.json

python -m cli.main character approve-design `
  --brief assets/character_creation_briefs/kaito.json `
  --manifest output/production/review/kaito-design-candidates.json `
  --candidate-key <selected-storage-key> `
  --approved-by <name> `
  --output output/production/review/kaito-canonical-approval.json

python -m cli.main character turnaround `
  --brief assets/character_creation_briefs/kaito.json `
  --approval output/production/review/kaito-canonical-approval.json `
  --manifest output/production/review/kaito-view-pack.json

python -m selma.cli approve-view-pack `
  --character kaito `
  --version v1 `
  --approved-by <name>
```

The local production root is configured with
`KEYFRAME_STORAGE_ROOT_DIR=output/production`. Model filenames and hashes come
only from `models.lock.json`.
