# SELMA Labs — Project Status

## Status Verdict
**`OPERATIONAL PIPELINE READY`**

---

## Current Scope Level
**Operational Integration of Sprint 1–17** (Git branch: `operational-integration`).
*Sprint 18 is pending and intentionally not implemented in this repository.*

---

## Validated Capabilities & Workflow Pipeline

1. **Unified End-to-End Orchestrator CLI** ([`scripts/run_pipeline.py`](file:///c:/Users/LOQ/Desktop/selma-labs-master/scripts/run_pipeline.py))
   - Supports live execution mode (Claude + ElevenLabs + Pexels + FFmpeg).
   - Supports 100% offline dry-run mode (`--dry-run`) with mock adapters.
   - Saves all artifacts into structured run directories (`output/<run-id>/`) with `metadata.json` and `run.log`.

2. **Sprint 1–17 Core Component Baseline**:
   - **Sprint 1: Script Generation** — `ScriptGeneratorPort`, `ClaudeScriptProvider`, `ScriptService`.
   - **Sprint 2: Voice Generation** — `VoiceGeneratorPort`, `StoragePort`, `ElevenLabsVoiceProvider`, `VoiceService`.
   - **Sprint 2.1: Caching Voice Decorator** — `CachingVoiceProvider`, `SpeechSegment` model.
   - **Sprint 3 / 3.1: Video Search** — `VideoSourcePort`, `PexelsProvider`, `MediaAsset`, `VideoSearchService`.
   - **Sprint 4: Scene Planning** — `ScenePlanningPort`, `ClaudeScenePlanningProvider`, `ScenePlan`, `ScenePlanningService`.
   - **Sprint 5: Asset Matching** — `AssetMatchPlan`, `SceneAssetMatch`, `SceneAssetMatchingService`.
   - **Sprint 6: Timeline Assembly** — `Timeline`, `TimelineClip`, `TimelineService`.
   - **Sprint 7: Video Rendering** — `RenderPort`, `FfmpegRenderProvider`, `RenderedVideo`, `RenderService`.
   - **Sprint 8: Subtitles** — `SubtitleTrack`, `SubtitleCue`, `SubtitleService`, `SubtitleFormatter`.
   - **Sprint 15.1–15.3: Asset Selection & Optimization** — `AssetSelectionService`, `AssetScore`, selection rules.
   - **Sprint 16: Search Cache** — `SearchCacheService`, `CacheKeyFactory`, `InMemoryCache`.
   - **Sprint 17: Resilient Search Orchestration** — `SearchOrchestratorService`, retry/backoff decorators.
   - **Subtitle Translation Extensions** — `SubtitleTranslationService`, `ClaudeTranslationProvider`, `CachingTranslationProvider`.

---

## Verified Test & Execution Metrics

- **Syntax Compilation Check**: 130 Python source files compiled with 0 errors.
- **Test Suite Results**:
  - **Collected**: 213 items
  - **Passed**: 213
  - **Failed**: 0
  - **Skipped**: 0
  - **Warnings**: 0

- **Verified CLI Entry Points**:
  - `python scripts/run_pipeline.py --help`
  - `python scripts/generate_script_test.py --help`
  - `python scripts/generate_voice.py --help`
  - `python scripts/search_assets.py --help`
  - `python scripts/plan_scenes.py --help`
  - `python scripts/match_assets.py --help`
  - `python scripts/create_timeline.py --help`
  - `python scripts/render_video.py --help`
  - `python scripts/generate_subtitles.py --help`
  - `python scripts/translate_subtitles.py --help`

- **Verified Execution Modes**:
  - `python scripts/run_pipeline.py "The mystery of the Mariana Trench" --dry-run --output output/mariana-trench-dry --target-languages es fr` (Exits 0 cleanly)
  - `python scripts/verify_pipeline.py` (Exits 0 cleanly)
