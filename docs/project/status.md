# Project Status

SELMA Labs is an active, local-first AI video production project. The codebase
supports both the durable topic/audio factory and a guarded Akira anime pipeline.

## Current baseline

| Area | Status |
|---|---|
| Python test suite | Verified by CI and the current branch test run |
| Python and real FFmpeg render CI | Passing on `main` |
| Remotion type-check and smoke frame CI | Passing on `main` |
| Topic/audio production factory | Implemented and live-validated |
| Akira character reference workflow | Implemented |
| Reference-driven character design | Dual anchors, chained seven-view generation, automatic QC, three-attempt quarantine/retry, contact sheet and atomic human approval implemented |
| Character production infrastructure | Model lock, fail-closed preflight, WebSocket watchdog/interrupt/retry, thermal guard, atomic manifest and exclusive work lock are wired to the live ComfyUI path |
| Character LoRA | Optional fallback; disabled in the default character path |
| Human keyframe approval boundary | Enforced and fail-closed |
| Two-pass ComfyUI motion workflow | Implemented and automated-test validated |
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

The active milestone is production hardening around the approved character
turnaround. Every view is screened before entering `views/`; rejected attempts
retain image and JSON evidence under `quarantine/`, and only a complete contact
sheet can receive `view-pack-approval.json`. Pose and animation work must verify
that receipt. LoRA is not required by the default path.

The live ComfyUI path currently reports `BLOCKED_PREFLIGHT`: the requested
Illustrious checkpoint, face detector and pose detector are not installed at
the paths recorded in `models.lock.json`. The installed IP-Adapter,
CLIP-Vision and OpenPose ControlNet entries have real SHA-256 locks.

See the [roadmap](roadmap.md) for the ordered work and the
[runbook](../operations/runbook.md) for environment setup.
