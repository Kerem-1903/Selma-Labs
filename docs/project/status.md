# Project Status

SELMA Labs is an active, local-first AI video production project. The codebase
supports both the durable topic/audio factory and a guarded Akira anime pipeline.

## Current baseline

| Area | Status |
|---|---|
| Python test suite | 684 tests passing |
| Python and real FFmpeg render CI | Passing on `main` |
| Remotion type-check and smoke frame CI | Passing on `main` |
| Topic/audio production factory | Implemented and live-validated |
| Akira character reference workflow | Implemented |
| Human keyframe approval boundary | Enforced and fail-closed |
| Two-pass ComfyUI motion workflow | Technically validated; perceptual motion QA still open |
| Controlled Akira motion test | 10-second Remotion render validated |
| FFmpeg layered composition | Real integration coverage |
| LivePortrait lip sync | Explicit mock/passthrough adapter |

## Production boundaries

- Provider-backed output requires the relevant local models, services, licensed
  inputs, and API credentials.
- The two-pass motion adapter will not run unless its keyframe is explicitly
  approved and persisted as `COMMITTED` by the human-review workflow.
- LivePortrait does not yet perform real mouth animation; the current adapter is
  intentionally labelled as a mock.
- Historical live-render measurements are preserved under
  [`docs/archive/status`](../archive/status/) and are not presented as current
  benchmark results.

## Current production target

The next milestone is a reviewable Akira pilot with approved keyframes,
controlled local motion generation, audio-driven character processing, layered
composition, and a reproducible delivery package.

See the [roadmap](roadmap.md) for the ordered work and the
[runbook](../operations/runbook.md) for environment setup.
