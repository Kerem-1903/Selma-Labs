# Character Factory

SELMA treats Akira as a calibration character, not as a special case. Every new
character follows the same gated pipeline:

1. Write a `CharacterBible` JSON with natural-language identity, silhouette,
   outfit and visual-style fields.
2. Create the deterministic onboarding plan. SELMA expands the Bible into one
   anchor prompt, 20 training recipes and 3 isolated holdout recipes.
3. Generate one anchor candidate and approve it manually. No unapproved anchor
   can be presented to the reference-pack command.
4. Generate all 23 reference candidates through the configured keyframe
   provider. The approved anchor is supplied to IP-Adapter for identity
   conditioning; filenames, prompts and seeds come from the plan.
5. Review the pack, build the LoRA dataset, train the LoRA, and run the generic
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
