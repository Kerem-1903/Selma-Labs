# SELMA Labs — Project Status

## Final Readiness Verdict
**`READY FOR SPRINT 18`**

---

## Current Sprint Level
**Sprint 17** (Consolidated Sprint 1–17 Stable Git Baseline).
*Sprint 18 is pending and intentionally not implemented in this repository.*

---

## Validated Capabilities

- **Sprint 1: Script Generation** — `ScriptGeneratorPort`, `ClaudeScriptProvider`, `ScriptService`, topic validation, word count ratio checks.
- **Sprint 2: Voice Generation** — `VoiceGeneratorPort`, `StoragePort`, `ElevenLabsVoiceProvider`, `LocalFsStorage`, `VoiceService`.
- **Sprint 2.1: Caching Voice Decorator** — `CachingVoiceProvider`, `SpeechSegment` model, JSON metadata storage.
- **Sprint 3 / 3.1: Video Search** — `VideoSourcePort`, `PexelsProvider`, `MediaAsset` identity + metadata extensions, `VideoSearchService`.
- **Sprint 4: Scene Planning** — `ScenePlanningPort`, `ClaudeScenePlanningProvider`, `ScenePlan`, `ScenePlanningService`, timing allocation.
- **Sprint 5: Asset Matching** — `AssetMatchPlan`, `SceneAssetMatch`, `SceneAssetMatchingService`, deterministic candidate ranking.
- **Sprint 6: Timeline Assembly** — `Timeline`, `TimelineClip`, `TimelineService`, candidate asset downloading & assignment per scene.
- **Sprint 7: Video Rendering** — `RenderPort`, `FfmpegRenderProvider`, `RenderedVideo`, `RenderResult`, `RenderService`.
- **Sprint 8: Subtitles** — `SubtitleTrack`, `SubtitleCue`, `SubtitleService`, `SubtitleFormatter` (SRT & WebVTT formatters).
- **Sprint 15.1–15.3: Asset Selection & Optimization** — `AssetSelectionService`, `AssetScore`, `ScoredAsset`, `AdjustedAssetScore`, selection rules.
- **Sprint 16: Search Cache** — `SearchCacheService`, `CacheKeyFactory`, `InMemoryCache`.
- **Sprint 17: Resilient Search Orchestration** — `SearchOrchestratorService`, retry/backoff decorators, multi-provider search fallback.
- **Subtitle Translation Extensions** — `SubtitleTranslationService`, `TranslatedSubtitleTrack`, `ClaudeTranslationProvider`, `CachingTranslationProvider`.

---

## Verified Test & Execution Metrics

- **Syntax Compilation Check**: 129 Python source files compiled with 0 errors.
- **Test Suite Results**:
  - **Collected**: 210 items
  - **Passed**: 210
  - **Failed**: 0
  - **Skipped**: 0
  - **Warnings**: 0 (Performance marker registered in `pyproject.toml`)

- **Verified CLI Entry Points**:
  - `python scripts/generate_script_test.py --help`
  - `python scripts/generate_voice.py --help`
  - `python scripts/search_assets.py --help`
  - `python scripts/plan_scenes.py --help`
  - `python scripts/match_assets.py --help`
  - `python scripts/create_timeline.py --help`
  - `python scripts/render_video.py --help`
  - `python scripts/generate_subtitles.py --help`
  - `python scripts/translate_subtitles.py --help`

- **Verified Offline Smoke Test**:
  - `python scripts/verify_pipeline.py` (Exits 0 cleanly from repository root)

- **Git Baseline**:
  - Initialized, committed baseline (`sprint-17-baseline` tag created).

---

## Environment & External Dependencies

| Service / Capability | Default Provider | Environment Variable | Requiring Credentials |
|---|---|---|---|
| Script Generation | Claude | `ANTHROPIC_API_KEY` | Real execution only (unit tests use fakes) |
| Voice Generation | ElevenLabs | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | Real execution only (unit tests use fakes) |
| Video Search | Pexels | `PEXELS_API_KEY` | Real execution only (unit tests use fakes) |
| Scene Planning | Claude | `ANTHROPIC_API_KEY` | Real execution only (unit tests use fakes) |
| Subtitle Translation | Claude | `ANTHROPIC_API_KEY` | Real execution only (unit tests use fakes) |
| Video Rendering | FFmpeg | Local `ffmpeg` binary on PATH | Local binary execution |
