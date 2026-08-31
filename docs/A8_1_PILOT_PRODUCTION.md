# A8.1 Publishable Pilot Production

A8.1 turns the A7-approved storyboard frame and A8 motion layer into a measured,
human-gated pilot workflow.

## Render profiles

| Profile | Resolution | Generated FPS | Sampling steps | Guidance |
| --- | ---: | ---: | ---: | ---: |
| `DRAFT` | 512x288 | 8 | 6 | 4.0 |
| `BALANCED` | 768x432 | 12 | 12 | 4.5 |
| `FINAL` | 1280x720 | 16 | 20 | 5.0 |

Profiles control real provider inputs. Higher delivery frame rates and resolution
upscaling remain post-production concerns so local previews do not waste GPU time.

## Production gate and retries

`ShotProductionService` delegates generation to
`ApprovedKeyframeMotionService`; an uncommitted A7 candidate cannot reach the
video provider. Only transient connection, timeout, and quota errors are retried
with exponential backoff. Validation and state errors fail immediately.

Every attempt records provider, profile, seed, elapsed seconds, result, error
details, and estimated cost using the configured hourly GPU price. The local JSON
repository writes this telemetry atomically for later cost-per-finished-minute
analysis.

## Human approval and assembly

Generated motion clips start as `PENDING_REVIEW`. A reviewer must create the
approved immutable form with `clip.approve()` and persist it before assembly.
`VideoAssemblerService` rejects every non-approved clip, retrieves inputs only
through `StoragePort`, normalizes mixed resolutions and frame rates with a bounded
FFmpeg process, concatenates the normalized files, and stores the final MP4 using
a portable storage key.
