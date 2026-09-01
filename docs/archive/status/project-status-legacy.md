# SELMA Labs — Project Status

## Verdict

**`PREMIUM YOUTUBE SHORTS FACTORY — LIVE VALIDATED`**

SELMA Labs now has one durable topic/audio production path. Topic runs cover
source-grounded fact checking, approved-script voice generation, WhisperX word
alignment, editorial storyboarding, English stock-search localization, AI Vision
quality gates, premium karaoke captions, single-pass FFmpeg rendering, content QA,
and a ready-to-review YouTube upload package.

## Production guarantees

- `scripts/run_factory.py` is the sole production composition root.
- Unsupported factual claims block before voice, search, and render costs.
- Paid stages are checkpointed; failed runs resume without repeating completed work.
- Fact-checked topic scripts must pass a persisted narrative contract before paid
  voice, search, or render stages can run.
- Completed runs can safely reprocess `VISION_SEARCH`, `RENDER`, or `UPLOAD_PACKAGE`.
- Turkish visual concepts are localized to concise English subject queries.
- OpenAI Vision can fall back to NVIDIA; NVIDIA images are contact-sheeted and kept
  within hosted endpoint limits.
- Vision rejects low-confidence, people/face, vehicle, text, logo, and watermark
  conflicts required by the visual brief.
- Evidence beats carry explicit visual jobs and required subject/action/relation
  evidence; a matching environment alone cannot satisfy the scene.
- Anatomy and mechanism beats require a diagram/overlay/hybrid explanation path,
  while unrelated dominant subjects are rejected before render.
- Strong verified clips may be reused with different phases before the system ever
  lowers a quality threshold.
- Perceptual frame hashes detect duplicate crops across different provider IDs;
  source, pose, camera-angle, and background budgets prevent cosmetic variety.
- Cuts align with spoken phrase/word boundaries, and long low-motion holds require
  a meaningful explanatory overlay.
- Captions and explanatory cards use restrained semantic animation; camera motion
  changes by visual job while hard cuts and the instant opening remain intact.
- Caption cues cannot cross sentence boundaries; real font/outline/scale metrics
  must fit the YouTube mobile safe zone before visual search begins.
- The final render produces nine caption-risk preview images across desktop,
  reduced, and 360×640 small-phone inspection sizes.
- Captions use 2–5 word phrases with active-word yellow/110% karaoke emphasis.
- Rendering is one H.264 High Profile CRF 17 pass with yuv420p, BT.709, `+faststart`,
  stereo AAC, narration processing, procedural accents, and -15 LUFS normalization.
- Post-render QA blocks opening black, excessive black, long freezes, long silence,
  invalid loudness, and unsafe peak levels.
- The YouTube package contains the MP4, SRT, title/description metadata, source
  credits, quality report, upload checklist, and a frame for Shorts thumbnail choice.

## Validation

- Python compilation: **0 errors**
- Automated suite: **429 passed / 0 failed**
- Live Turkish topic run: **COMPLETED**
- Final media: **1080×1920, 30 fps, H.264/AAC, 26.610 s**
- Content QA: **-15.2 LUFS, 0.0 s opening black, 0.8313 s max silence,
  1.2333 s max freeze, -4.5 dBFS peak**
- Upload package: **ready_to_upload = true; all required checks PASS**

## External production input still required

Add publishable music files and `assets/music/license_manifest.json` to enable a
licensed background bed. Until then, topic runs deliberately record the reason and
render narration-only; they never substitute unlicensed audio.
