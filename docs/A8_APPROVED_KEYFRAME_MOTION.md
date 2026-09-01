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

To exercise the guarded two-pass adapter directly with Akira's approved front
reference, run the reproducible local smoke test:

```text
python scripts/two_pass_motion_smoke.py --confirm-human-approved
```

The default run requests a 10-second, 384x896 portrait, 6 FPS clip with seed `1903` and
writes both the video and an FFprobe-backed JSON evidence report under
`output/two_pass_smoke`. The bundled workflow uses 16-frame overlapping
AnimateDiff context windows and supports at most 64 frames per run. The explicit
approval flag is mandatory: the script creates, approves, and commits a fresh A7
candidate before any GPU work is queued.

## Reference local validation

The workflow was exercised on 2026-09-01 with an RTX 4060 Laptop GPU (8 GB):

- 60/60 distinct frames, 10.000 seconds, H.264, 384x896, 6 FPS;
- two-pass execution time: 721.765 seconds;
- seed: `1903`;
- output SHA-256:
  `3d03db4de13f0e9ef2e4f790c2ccfef4daa8bf516c0192d29fee77f56a1444c0`.

This run validates the provider, approval gate, model loading, two-pass graph,
video encoding, and metadata contracts. It did **not** pass perceptual motion QA:
the low-denoise output was visually too static. A stronger-denoise rerun created
temporal flicker instead of coherent character motion. Neither AI result is
treated as an accepted animation sample.

The accepted visible 10-second motion test is the deterministic Remotion
composition `AkiraMotionTest`, which animates the approved reference with a
controlled camera move, sway/breathing scale, scan light, grid, and particles.
Render it with:

```text
cd motion
npm run render:akira
```

The output media remains a local review artifact rather than a repository blob.
Re-run the command above to reproduce it with the installed, licensed models.
