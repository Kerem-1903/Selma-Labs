# Character Factory

SELMA treats Akira as a calibration character, not as a special case. Every new
character follows the same gated pipeline:

Generated reference candidates are checked by the configured vision model.
Identity/framing or subject-policy failures are written to the run's
`quarantine` directory and regenerated with a deterministic alternate seed, up
to three attempts. Passing the automatic gate does not approve the character:
the reference pack still requires explicit human selection.

1. Write a `CharacterBible` JSON with natural-language identity, silhouette,
   outfit and visual-style fields.
2. Create the deterministic onboarding plan. SELMA expands the Bible into one
   anchor prompt, 20 training recipes and 3 isolated holdout recipes.
3. Generate one anchor candidate and approve it manually. No unapproved anchor
   can be presented to the reference-pack command.
4. Generate only the first face-closeup pilot. SELMA sends a portrait-specific
   camera/lens contract and separate face, hair, immutable-mark, outfit and
   framing locks to the image provider.
5. Review the pilot against all six checks and create a signed approval receipt.
   Full generation is rejected if the receipt, anchor or pilot hash has changed.
6. Generate the remaining 22 reference candidates through the configured
   keyframe provider. The approved pilot is reused as candidate one.
7. Review the pack, build the LoRA dataset, train the LoRA, and run the generic
   ten-shot Golden Set. Only a passing, human-approved Golden Set may be locked.

## Commands

```powershell
python -m cli.main character init `
  --brief assets/character-brief.example.json `
  --output assets/character_bibles/nova.json

python -m cli.main character plan `
  --input assets/character_bibles/akira.json `
  --output output/characters/akira/onboarding-plan.json

python -m cli.main character anchor `
  --input assets/character_bibles/akira.json

python -m cli.main character references `
  --input assets/character_bibles/akira.json `
  --approved-anchor-key '<key printed by the anchor command>' `
  --limit 1 `
  --defer-visual-review `
  --manifest output/characters/akira/pilot.json

python -m cli.main character approve-pilot `
  --input assets/character_bibles/akira.json `
  --approved-anchor-key '<approved anchor key>' `
  --pilot-key '<pilot storage key>' `
  --approved-by Kerem `
  --face-match --hair-match --immutable-marks-match `
  --outfit-match --framing-match --anatomy-pass `
  --output output/characters/akira/pilot-approval.json

python -m cli.main character references `
  --input assets/character_bibles/akira.json `
  --approved-anchor-key '<approved anchor key>' `
  --pilot-approval output/characters/akira/pilot-approval.json `
  --manifest output/characters/akira/candidate-pack.json

python -m cli.main character approve-references `
  --input assets/character_bibles/nova.json `
  --selections assets/character-reference-selection.example.json `
  --approved-by Kerem `
  --lock-narrative `
  --output assets/character_bibles/nova.json

python -m cli.main character dataset `
  --input assets/character_bibles/akira.json `
  --source '<source directory printed in the candidate manifest>' `
  --output output/training/akira-lora-v1

python -m cli.main character train `
  --input assets/character_bibles/akira.json `
  --dataset output/training/akira-lora-v1 `
  --base-model C:/models/animagine-xl-4.0-opt.safetensors `
  --sd-scripts-dir C:/tools/sd-scripts `
  --output output/training/akira-lora-v1/model `
  --model-name selma-akira-v1

python -m cli.main preproduction golden-set `
  --character-id akira `
  --model-id selma-akira-v1 `
  --model-revision v1
```

Use `KEYFRAME_GENERATION_PROVIDER=comfyui` for real local generation. The fake
provider remains available for offline pipeline tests. Candidate manifests keep
`human_approved: false`; selecting and approving an anchor or Golden Set remains
an explicit human decision.

## What is character-specific?

Only the Character Bible and the final human approvals. Dataset view coverage,
prompt expansion, deterministic seeds, storage layout, LoRA captions, holdout
separation and Golden Set scenarios are shared by every character.
