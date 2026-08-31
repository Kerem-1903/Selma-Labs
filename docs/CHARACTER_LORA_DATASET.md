# Character LoRA Dataset Foundation

This layer prepares original SELMA character references for reviewable LoRA
training. It does not start training and does not treat a small reference pack
as a production-ready dataset.

## Build a dataset

```powershell
python scripts/build_character_lora_dataset.py `
  --source assets/references/akira `
  --output output/training/akira-lora-v1 `
  --character-id akira `
  --trigger-token selma_akira_v1
```

The command writes normalized 1024×1024 images, matching caption files and an
atomic `manifest.json`. Exit code `0` means the dataset meets the configured
training and holdout counts. Exit code `2` means the dataset was built but must
not be trained yet.

The default quality gate requires:

- at least 20 independent training images;
- at least 3 holdout images that never enter training;
- no unreadable, undersized or unknown-view assets;
- no duplicate image content;
- `original_character` rights status.

Master sheets and pose-control images are intentionally excluded. Generated
variants should not be added automatically: each candidate needs human review
for face geometry, scar side, hair streak side, outfit, anatomy and unintended
props.

## Enable a trained LoRA

Place the approved `.safetensors` file in ComfyUI's `models/loras` directory and
set:

```dotenv
COMFYUI_CHARACTER_LORA_NAME=selma-akira-v1.safetensors
COMFYUI_CHARACTER_LORA_TRIGGER_TOKEN=selma_akira_v1
COMFYUI_CHARACTER_LORA_STRENGTH_MODEL=0.8
COMFYUI_CHARACTER_LORA_STRENGTH_CLIP=0.8
```

The workflow keeps the LoRA node disconnected while the name is blank. When a
name is configured, the provider connects the LoRA before IP-Adapter and routes
both positive and negative CLIP conditioning through it.

For action shots, requests can set `visual_constraints.identity_mode` to
`identity_only`. This reduces IP-Adapter composition transfer, but a Character
LoRA remains the long-term identity mechanism.
