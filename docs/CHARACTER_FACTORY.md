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
   contract containing identity and framing locks; face-only prompts never
   inherit full-body, costume, boot, or weapon claims.
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

Use `--seed-offset 10000` and `--seed-offset 20000` with separate pilot
manifests to create reproducible alternatives without changing the identity
contract.

Use `KEYFRAME_GENERATION_PROVIDER=comfyui` for real local generation. Anime
characters use `assets/comfyui_keyframe_workflow.json`: standard visual
IP-Adapter in `identity_only` mode, the locked reference encoded as the img2img
latent, moderate denoise, and OpenPose where a recipe has a reviewed pose map.
This lets composition move without asking a face-recognition model to understand
anime geometry. The fake
provider remains available for offline pipeline tests. Candidate manifests keep
`human_approved: false`; selecting and approving an anchor or Golden Set remains
an explicit human decision.

`--defer-visual-review` is diagnostic only. It writes one unaudited frame under
`quarantine/`; that frame cannot pass `approve-pilot`, `approve-references`, or
enter a dataset. With the default automatic review, failed frames are reseeded
up to three times and remain quarantined if all attempts fail.

For human-realistic portrait pilots whose reference face is detectable by
InsightFace, select
`assets/comfyui_keyframe_faceid_workflow.json` with
`COMFYUI_KEYFRAME_WORKFLOW_PATH`. This workflow uses FaceID Plus V2 to lock
facial geometry while the Character Bible continues to control hair, outfit,
palette and immutable marks. It requires the FaceID Plus V2 SDXL IP-Adapter,
its matching technical LoRA, InsightFace `buffalo_l`, and the ComfyUI
IPAdapter Plus custom nodes. FaceID is an identity aid, not human approval: a
pilot with a misplaced hair mark or invented costume detail must still fail.
Do not use FaceID for anime characters: `NO_HEAD` is a model-domain mismatch,
not evidence that the anime drawing lacks a face. Anime candidates instead pass
the configured vision/QA evaluator and later a human-reviewed Golden Set. The
structured-mark seal derives its head region from InsightFace, so anime golden
runs disable it with `GOLDEN_MARKER_GATE_ENABLED=false`; when a head region
cannot be detected the gate reports `marker_gate_passed: false` with a note
rather than aborting the run, and only a human-locked, passing set may seal a
model. The visual workflow accepts a reviewed OpenPose image through
`pose_storage_key`, allowing facial identity and acting pose to be controlled
in one render.

Neutral, face, upper-body, and profile recipes may run now. Action recipes must
wait until their `pose_reference_key` exists in the pose manifest. Katana-ready
and running are present; remaining action skeletons must come from licensed pose
photos or SELMA's own rig renders before those recipes are enabled.

When an otherwise usable anchor conflicts with one local immutable mark, repair
only a reviewed mask before running the pilot again:

```powershell
python scripts/comfyui_region_repair.py `
  --input path/to/anchor.png `
  --mask path/to/reviewed-white-mask.png `
  --output output/training/repaired-anchor.png `
  --checkpoint animagine-xl-4.0-opt.safetensors `
  --prompt "continuous black hair matching the surrounding strands"
```

White mask pixels are regenerated; black pixels are preserved. The repaired
anchor is a new candidate and requires human approval—it never silently
replaces an approved source.

## What is character-specific?

Only the Character Bible and the final human approvals. Dataset view coverage,
prompt expansion, deterministic seeds, storage layout, LoRA captions, holdout
separation and Golden Set scenarios are shared by every character.
