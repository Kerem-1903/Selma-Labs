# SELMA Labs — Operations & Developer Runbook

This runbook provides step-by-step instructions to set up, validate, test, and run the SELMA Labs Sprint 1–17 master codebase locally.

---

## 1. Operational Integration Overview (Sprint 1–17)

The repository provides a unified end-to-end execution path ([`scripts/run_pipeline.py`](file:///c:/Users/LOQ/Desktop/selma-labs-master/scripts/run_pipeline.py)) connecting all Sprint 1–17 capabilities into a single command for producing vertical video Shorts.

### Intended User Flow:
1. User provides a topic.
2. Generate short-form script.
3. Retrieve relevant Wikipedia evidence and fact-check every script claim with NVIDIA 70B plus an independent 90B audit.
4. Rewrite failed claims only from retrieved evidence and run the independent fact check again.
5. Stop before paid media generation if unsupported claims remain after the configured retries.
6. Generate narration audio.
7. Plan scenes from narration timing.
8. Search visual media for each scene.
9. Match & rank candidates using deterministic rules and optional AI Vision.
10. Build clip timeline with download fallback candidates.
11. Generate & format subtitles (SRT/WebVTT).
12. Render vertical video (1080x1920 MP4) with burned-in captions.
13. Optionally translate subtitles to additional languages.
14. Validate duration, 9:16 geometry, MP4/H.264/AAC, captions, and source rights metadata.
15. Create a self-contained `publish/` package and save run metadata.

---

## 2. Environment Setup

- **Python Version**: Python 3.10 or higher.
- **FFmpeg (Required for Live Video Rendering)**: Ensure `ffmpeg` and `ffprobe` binaries are on system `PATH`.
- **Usage Model**: Source repository executed directly from its root.

```bash
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 3. Environment Variables & Credentials (.env)

Copy `.env.example` to `.env` in the repository root:
```bash
cp .env.example .env
```

```env
# NVIDIA text, audit, and optional Vision models
SCRIPT_PROVIDER=nvidia
SCENE_PLANNING_PROVIDER=nvidia
TRANSLATION_PROVIDER=nvidia
NVIDIA_API_KEY=your_nvidia_api_key_here
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_TEXT_MODEL=meta/llama-3.3-70b-instruct
NVIDIA_VISION_MODEL=nvidia/llama-3.1-nemotron-nano-vl-8b-v1
NVIDIA_TIMEOUT_SECONDS=180

# Source-grounded fact checking
FACT_SOURCE_PROVIDER=wikipedia
FACT_CHECK_PROVIDER=nvidia
FACT_CHECK_SOURCE_LANGUAGE=en
FACT_CHECK_SOURCE_LIMIT=5
FACT_CHECK_MAX_EXTRACT_CHARS=5000
FACT_CHECK_REWRITE_ATTEMPTS=2

# Premium creative profile
SCENE_MIN_VISUAL_BEATS=3
SUBTITLE_MAX_CHARS_PER_LINE=24
SUBTITLE_MAX_LINES_PER_CUE=1
SUBTITLE_MIN_CUE_SECONDS=0.8
BACKGROUND_MUSIC_PROVIDER=local
BACKGROUND_MUSIC_DIR=assets/music
AUDIO_MIX_PROVIDER=ffmpeg

# YouTube trend discovery
YOUTUBE_DATA_API_KEY=your_youtube_data_api_key_here
TREND_REGION_CODE=US
TREND_SEARCH_QUERY=science facts|animal facts|nature facts
TREND_RELEVANCE_LANGUAGE=en
TREND_PUBLISHED_WITHIN_DAYS=30

# ElevenLabs Voice API Key & Defaults
VOICE_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
ELEVENLABS_MODEL_ID=eleven_multilingual_v2

# Pexels Video Search API Key
VIDEO_PROVIDER=pexels
PEXELS_API_KEY=your_pexels_api_key_here
DEFAULT_VIDEO_MAX_RESULTS=10
SEARCH_CACHE_ENABLED=true
SEARCH_CACHE_TTL_SECONDS=300
SEARCH_CACHE_NEGATIVE_TTL_SECONDS=60
PROVIDER_TIMEOUT_SECONDS=15
PROVIDER_MAX_RETRIES=2

# Storage & Caching Configuration
STORAGE_ROOT_DIR=output
VOICE_CACHE_ENABLED=true
VOICE_CACHE_DIR=cache/voice

# Optional AI Vision rescoring (disabled by default to control API cost)
VISION_ENABLED=false
VISION_PROVIDER=nvidia
VISION_TOP_CANDIDATES=5
VISION_FRAMES_PER_ASSET=3

# Remotion creative composition + FFmpeg delivery mastering
RENDER_PROVIDER=remotion
FFMPEG_BINARY_PATH=ffmpeg
FFPROBE_BINARY_PATH=ffprobe
REMOTION_PROJECT_DIR=motion
REMOTION_CLI_PATH=
REMOTION_SUBPROCESS_TIMEOUT_SECONDS=900
RENDER_OUTPUT_WIDTH=1080
RENDER_OUTPUT_HEIGHT=1920
RENDER_FPS=30
```

---

## 4. Running the End-to-End Pipeline

### Production Factory (recommended)

```powershell
python scripts/run_factory.py --topic "Ahtapotların neden üç kalbi var?" --language tr --duration-seconds 30
python scripts/run_factory.py --audio-path .\licensed.wav

# Resume a failed durable run without repeating completed stages
python scripts/run_factory.py --topic "Ahtapot" --run-id <UUID>

# Explicitly add recovery budget after an external outage
python scripts/run_factory.py --topic "Ahtapot" --run-id <UUID> --additional-retries 2

# Re-run only downstream creative stages of a completed/failed run
python scripts/run_factory.py --topic "Ahtapot" --run-id <UUID> --reprocess-from VISION_SEARCH
```

The factory writes durable state under `.selma_runs/`, final media under `output/`,
and a `<run-id>_youtube/` upload package for successful topic runs.

### A. Local Dry-Run Mode (100% Offline, No API Keys Required)
Exercises the full user-facing pipeline using in-memory mock adapters without network calls or credentials:
```bash
python scripts/run_pipeline.py "The mystery of the Mariana Trench" --dry-run --vision balanced --output output/mariana-trench-dry --target-languages es fr
```

### B. Live Pipeline Mode (Requires API Credentials & FFmpeg)
Executes against live NVIDIA, Wikipedia, ElevenLabs, Pexels, and local FFmpeg:
```bash
python scripts/run_pipeline.py "The mystery of the Mariana Trench" --vision balanced --output output/mariana-trench --target-languages es fr
```

Select a live trend-derived topic and run the full pipeline:
```bash
python scripts/run_pipeline.py --auto-topic --output output/auto-topic-live

# Premium mode (requires assets/music/license_manifest.json)
python scripts/run_pipeline.py --auto-topic --quality premium --vision balanced --output output/premium-live
```

Preview a trend-derived topic without creating a video:
```bash
python scripts/discover_trending_topic.py --region US --language en
```

### Options & Flags (`python scripts/run_pipeline.py --help`):
- `topic`: Positional argument or `--topic` flag.
- `--output / -o`: Custom run directory path (defaults to `output/<sanitized_topic>_<run_id>`).
- `--duration`: Target spoken duration in seconds (15–90).
- `--voice-id`: Override default ElevenLabs voice ID.
- `--language`: Primary subtitle language code (default `en`).
- `--target-languages`: Additional target languages for subtitle translation (e.g. `--target-languages es fr de`).
- `--candidates-per-scene`: Max candidates evaluated per scene before ranking (default 10).
- `--dry-run`: Run offline using mock adapters without network or credentials.
- `--vision off|balanced`: Disable or enable AI Vision rescoring for the strongest candidates.
- `--burn-subtitles / --no-burn-subtitles`: Burn primary captions into the MP4 (enabled by default).
- `--made-for-kids / --no-made-for-kids`: Prepare the YouTube audience flag (defaults to not made for kids; review before publishing).
- `--auto-topic`: Select an original topic from recent popular science/nature/animal short videos.

The pipeline accepts either a manual topic or `--auto-topic`. YouTube account
publishing remains a separate future stage.

---

## 5. Run Directory Structure & Metadata

Every pipeline execution generates a self-contained output directory:

```
output/<run-dir>/
├── script/
│   ├── script.json         # Raw Script entity JSON metadata
│   ├── script.txt          # Plain narration text
│   └── fact_check_report.json # Claim verdicts, evidence quotes, and source URLs
├── voice/
│   └── <script-and-audio-id>.mp3 # Generated voice audio track
├── scenes/
│   └── scene_plan.json     # Timed scenes with keywords, mood & priority
├── assets/
│   └── asset_match_plan.json # Candidate media asset matches per scene
├── timeline/
│   └── timeline.json       # Ordered clips with selection scores
├── subtitles/
│   ├── subtitles_en.srt    # Primary SRT subtitles
│   ├── subtitles_en.vtt    # Primary WebVTT subtitles
│   ├── subtitles_es.srt    # Translated SRT subtitles (if requested)
│   └── subtitles_es.vtt    # Translated WebVTT subtitles (if requested)
├── render/
│   └── <rendered-video-id>.mp4 # Persisted vertical rendered video
├── publish/
│   ├── youtube_short.mp4   # Upload file: 9:16 H.264/AAC MP4
│   ├── captions_en.srt     # YouTube Studio sidecar captions
│   ├── youtube_metadata.json # Title, description, tags and upload settings
│   ├── quality_report.json # Automated technical readiness checks
│   ├── upload_checklist.md # Required human review before publishing
│   └── thumbnail_selection_frame.jpg # Frame-selection reference
├── metadata.json           # Execution status, stage metrics & relative file paths
└── run.log                 # Human-readable pipeline execution log
```

---

## 6. Offline vs. External Requirements & Failure Handling

| Stage | Offline (Dry-Run) Adapter | Live Provider Adapter | External Requirement |
|---|---|---|---|
| Script Generation | `DryRunScriptGenerator` | `ClaudeScriptProvider` | `ANTHROPIC_API_KEY` |
| Voice Generation | `DryRunVoiceGenerator` | `ElevenLabsVoiceProvider` | `ELEVENLABS_API_KEY` |
| Scene Planning | `DryRunScenePlanner` | `ClaudeScenePlanningProvider` | `ANTHROPIC_API_KEY` |
| Video Search & Download | `DryRunVideoSource` | `PexelsProvider` | `PEXELS_API_KEY` |
| Asset Matching | Rules + optional fake Vision | Rules + optional Claude Vision | `ANTHROPIC_API_KEY` only when Vision is enabled |
| Search Reliability | In-memory cache + retry | In-memory cache + retry | None beyond the video provider |
| Timeline Assembly | Ranked fallback mapping | Ranked fallback mapping | None (In-process) |
| Video Rendering | `DryRunRenderProvider` | `FfmpegRenderProvider` | Local `ffmpeg` binary |
| Subtitle Generation | `SubtitleService` | `SubtitleService` | None (In-process) |
| Subtitle Translation | `DryRunTranslationProvider` | `ClaudeTranslationProvider` | `ANTHROPIC_API_KEY` |
| Upload Preparation | Fake valid inspection | FFmpeg/ffprobe inspection | Local `ffmpeg` and `ffprobe` binaries |

### Common Failure Messages & Recovery:
- **`ProviderAuthError: API key is required`**: Missing credential in `.env`. Add key or run with `--dry-run`.
- **`ScriptGenerationError: Generated script has X words...`**: Model output violated spoken word count range. Re-run or adjust `--duration`.
- **`RenderError: ffmpeg binary not found`**: FFmpeg not installed on PATH. Install FFmpeg or run with `--dry-run`.
- **`SubtitleTranslationError: Cue count mismatch`**: Provider returned unexpected cue count during translation. Re-run or check model settings.

On any stage failure, `run_pipeline.py` logs the exact error to `run.log`, prints an actionable error message, writes partial `metadata.json` with status `"FAILED"`, and exits with code 1 without corrupting earlier stage outputs.

---

## 7. Running Tests & Validation

```bash
# Run the full suite (429 tests after Sprint 21 mobile-caption integration)
pytest

# Run repository internal pipeline smoke test
python scripts/verify_pipeline.py
```
