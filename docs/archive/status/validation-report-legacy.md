# SELMA Labs — Premium Factory Validation Report

## Executive summary

- Status: **LIVE END-TO-END VALIDATED**
- Automated tests: **429 passed / 0 failed**
- Syntax compilation: **0 errors**
- Production entry point: `scripts/run_factory.py`
- Live run ID: `909f7422-0637-48ba-b1cf-553bcd51160e`
- Live run status: **COMPLETED**
- YouTube package: **ready_to_upload = true**

## Live validation path

The Turkish topic `Ahtapotların neden üç kalbi var?` was processed through:

1. NVIDIA script generation.
2. Wikipedia evidence retrieval, claim audit, and two grounded rewrites.
3. ElevenLabs narration.
   Before this paid stage, the verified script now passes the durable
   `NARRATIVE_QUALITY_V1` hook, answer, density, and payoff contract.
4. WhisperX alignment against the approved Turkish script.
5. 2–5 word karaoke cue partitioning.
6. Gap-free editorial scene planning.
   Current code now enriches these scenes with semantic visual jobs, required
   subjects/actions/relations, explanatory modes, and forbidden dominant objects.
7. Topic-anchored English stock-search localization.
8. Pexels portrait discovery and NVIDIA Vision scoring with forbidden-content gates.
   Current code additionally records perceptual identity, pose, camera angle,
   background, and representative-frame motion energy before the durable
   `EDITORIAL_RHYTHM_V1` gate.
9. Licensed-music lookup with explicit narration-only fallback.
10. Single-pass FFmpeg render and procedural audio accents.
11. Technical inspection plus black/freeze/silence/loudness QA.
12. YouTube upload packaging with rights metadata and captions.

## Final media results

| Check | Result |
|---|---:|
| Container / codecs | MP4 / H.264 / AAC |
| Resolution | 1080×1920 |
| Frame rate | 30.000 fps |
| Duration | 26.610 s |
| Audio sample rate | 48 kHz |
| Audio bitrate | 249,762 bps |
| Integrated loudness | -15.2 LUFS |
| True peak | -4.5 dBFS |
| Opening black | 0.0 s |
| Total black | 0.0 s |
| Longest freeze | 1.2333 s |
| Longest silence | 0.8313 s |

Every required upload-package check passed, including file integrity, Shorts duration,
9:16 orientation, H.264/AAC compatibility, metadata lengths, source-rights evidence,
thumbnail selection frame, and Turkish SRT captions.

The media measurements above belong to the earlier live validation artifact. Sprint
19's semantic storyboard implementation is fully automated-test validated; its newly
rendered multi-topic visual score will be recorded during the Sprint 25 benchmark.
Sprint 20's diversity and rhythm implementation is validated by the same automated
suite; the historical media measurements above still predate its regenerated render.
The subsequent semantic animation layer has also passed a real local ASS/FFmpeg
render test; benchmark creative scoring still requires the regenerated final video.
Sprint 21 adds durable caption UX and preview stages: hard sentence boundaries,
styled safe-zone measurement, short-word no-scale handling, and three risk samples
at three display sizes are automated-test validated.

## Recovery findings resolved during live validation

- Turkish Wikipedia fallback was added when English topic search returned no source.
- Cross-thread file locks were corrected for async worker usage.
- OpenAI quota failure now circuit-breaks to NVIDIA Vision.
- NVIDIA's one-image/180 KB hosted limits are handled with compressed contact sheets.
- NVIDIA JSON refusals and labeled Markdown responses have bounded recovery.
- Stock searches are localized and anchored to the global topic.
- Thumbnail preflight avoids scanning entire remote videos during candidate scoring.
- Low-quality uniqueness now yields to verified phased reuse without lowering thresholds.
- People/face, vehicle, text, logo, and watermark conflicts are rejected.
- MP3 timing discrepancies up to 50 ms are safely clamped at render boundaries.
- Completed runs can reprocess downstream stages without repeating paid upstream stages.

## Remaining external dependency

No real licensed background-music manifest is currently installed. The validated run
therefore used the designed narration-only fallback. Adding publishable tracks plus
`assets/music/license_manifest.json` is an asset/licensing task, not a code blocker.
