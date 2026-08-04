# Current Status

## Completed

**Sprint 1**
- Script Generation
- Claude provider
- ScriptService
- Tests

**Sprint 2**
- Voice Generation
- ElevenLabs
- StoragePort
- VoiceService
- Tests

**Sprint 2.1**
- CachingVoiceProvider
- SpeechSegment model
- JSON export
- Decorator cache
- Tests

**Sprint 3**
- Video Search
- Pexels provider
- MediaAsset
- VideoSearchService
- Tests

**Sprint 4**
- Scene Planning
- ScenePlan
- ScenePlanningService
- ClaudeScenePlanningProvider
- Timeline estimation
- Tests

**Sprint 5**
- Scene Asset Matching
- AssetMatchPlan
- SceneAssetMatch
- VideoSearchService.search()
- Deterministic ranking
- match_assets.py
- Tests

**Sprint 6**
- Timeline Creation
- Timeline / TimelineClip
- VideoSearchService.download()
- TimelineService
- create_timeline.py
- Tests

**Sprint 7**
- Video Rendering
- RenderResult / RenderedVideo
- RenderPort / FfmpegRenderProvider
- RenderService
- render_video.py
- Tests

**Sprint 8**
- Automatic Subtitle Generation
- SubtitleTrack / SubtitleCue
- SubtitleFormatter (SRT/WebVTT, no new Port)
- SubtitleService
- generate_subtitles.py
- render_video.py --subtitle flag
- Tests

## Current total

174 passing tests

Architecture remains frozen.

## Next sprint

Nothing scoped yet. The pipeline (Script -> VoiceTrack -> ScenePlan ->
AssetMatchPlan -> Timeline -> RenderedVideo, with SubtitleTrack as a
parallel branch off ScenePlan) is now end-to-end complete through
rendering and subtitle export. Candidate future directions named in prior
sprints' "Future Enhancements" sections (unmatched-scene recovery, AI
Vision ranking, render engine fallback, hard-burned captions,
SubtitleStyle, translated subtitles, transitions/music, YouTube
publishing) are not yet sequenced into a sprint.

Do not redesign previous sprints.

Do not change public APIs unless absolutely necessary.

Explain architectural reasoning before code changes.
