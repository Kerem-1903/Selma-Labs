# Premium YouTube Shorts Pipeline

## Hexagonal Directory Structure

```text
core/
  domain/
    entities/                 # Script, VoiceTrack, ScenePlan, Timeline
    value_objects/            # Fact reports, music tracks, quality reports
    ports/                    # Provider-independent contracts
      script_generator_port.py
      script_rewriter_port.py
      fact_source_port.py
      fact_check_port.py
      voice_generator_port.py
      video_source_port.py
      vision_analysis_port.py
      background_music_port.py
      audio_mix_port.py
      render_port.py
  application/
    services/                 # Use cases and production policy
      script_fact_check_service.py
      scene_planning_service.py
      premium_shorts_quality_service.py
      audio_experience_service.py
      subtitle_service.py
      render_service.py
infrastructure/
  providers/                  # Driven adapters
    script/                   # NVIDIA text generation and grounded rewrite
    fact_check/               # NVIDIA independent claim verification
    voice/                    # ElevenLabs emotive TTS
    video/                    # Pexels portrait Full-HD footage
    vision/                   # NVIDIA contextual visual scoring
    music/                    # Licensed local music library
    audio_mix/                # FFmpeg ducking and loudness normalization
    render/                   # FFmpeg 9:16 composition
scripts/
  run_pipeline.py             # Composition root; no domain policy
assets/music/                 # Licensed tracks and mandatory manifest
```

## Premium Invariants

- A source-grounded hook must resolve within the first 3.2 seconds.
- Every visual beat must be 3.5 seconds or shorter.
- Every Pexels source must be portrait and at least 1080x1920.
- Adjacent scenes cannot reuse the same asset; at least 60% must be unique.
- Captions contain at most six words and three seconds per cue.
- Premium ASS captions highlight each spoken word and support contextual emoji.
- Background music must have explicit attribution and license metadata.
- Music theme is selected from topic, verified script, and scene moods; confidence,
  rationale, and override state are written to run metadata.
- Music is side-chain ducked under speech and the final mix is normalized to -16 LUFS.
- Any failed invariant blocks rendering and writes `quality/premium_quality_report.json`.

## Premium Execution

1. Add commercially licensed music and create `assets/music/license_manifest.json`.
2. Configure API credentials in `.env` without committing the file.
3. Run:

```powershell
python scripts/run_pipeline.py --auto-topic --quality premium --vision balanced
```

Optional overrides: `--music-theme mystery|wonder|energy` and
`--music-track <manifest title-or-filename>`.

NVIDIA is used behind text, fact-check, scene-planning, and visual-analysis
adapters. FFmpeg remains the deterministic local rendering adapter.
