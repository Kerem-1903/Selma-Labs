# A8 Approved Keyframe Motion

A8 converts only an A7-approved and committed storyboard frame into a durable
video clip. The legacy text-to-video provider remains untouched so the existing
Short-Form Factory can continue to use it independently.

The default provider is offline and deterministic:

```env
IMAGE_TO_VIDEO_PROVIDER=fake
```

For a real local render, export a ComfyUI API-format image-to-video workflow and
configure it with:

```env
IMAGE_TO_VIDEO_PROVIDER=comfyui
COMFYUI_I2V_WORKFLOW_PATH=assets/comfyui_i2v_workflow.json
```

The workflow must contain a `LoadImage` node, a positive `CLIPTextEncode` node,
and a video-output node that reports an MP4 or WebM file in ComfyUI history.
Frame-count fields (`num_frames`, `length`, or `frames`), FPS fields, and sampler
seed fields are filled when present. Model checkpoints and model-specific nodes
remain in the exported workflow rather than leaking into the domain layer.

After completing the A7 smoke test, run:

```text
python scripts/a8_akira_i2v_smoke.py --storyboard-id <storyboard-id>
```

The script fails with a non-zero exit code when the workflow, ComfyUI service,
committed candidate, source image, generated video, or metadata persistence is
invalid.
