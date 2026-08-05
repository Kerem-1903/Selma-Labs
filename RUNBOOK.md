# SELMA Labs — Operations & Developer Runbook

This runbook provides step-by-step instructions to set up, validate, test, and run the SELMA Labs Sprint 1–17 master codebase locally.

---

## 1. Operational Integration Overview (Sprint 1–17)

The repository provides a unified end-to-end execution path ([`scripts/run_pipeline.py`](file:///c:/Users/LOQ/Desktop/selma-labs-master/scripts/run_pipeline.py)) connecting all Sprint 1–17 capabilities into a single command for producing vertical video Shorts.

### Intended User Flow:
1. User provides a topic.
2. Generate short-form script.
3. Generate narration audio.
4. Plan scenes from narration timing.
5. Search visual media for each scene.
6. Match & rank candidates to scenes.
7. Build clip timeline.
8. Render vertical video (1080x1920 MP4).
9. Generate & format subtitles (SRT/WebVTT).
10. Optionally translate subtitles to additional languages.
11. Save all outputs in an organized run directory with `metadata.json` & `run.log`.

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
# Anthropic API Key (Claude for Script Generation, Scene Planning, Subtitle Translation)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
CLAUDE_SCRIPT_MODEL=claude-sonnet-4-5
SCENE_PLANNING_MODEL=claude-sonnet-4-5

# ElevenLabs Voice API Key & Defaults
VOICE_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
ELEVENLABS_MODEL_ID=eleven_multilingual_v2

# Pexels Video Search API Key
VIDEO_PROVIDER=pexels
PEXELS_API_KEY=your_pexels_api_key_here
DEFAULT_VIDEO_MAX_RESULTS=10

# Storage & Caching Configuration
STORAGE_ROOT_DIR=output
VOICE_CACHE_ENABLED=true
VOICE_CACHE_DIR=cache/voice

# Subtitle Translation Switch
TRANSLATION_PROVIDER=claude

# FFmpeg Rendering Parameters
RENDER_PROVIDER=ffmpeg
FFMPEG_BINARY_PATH=ffmpeg
FFPROBE_BINARY_PATH=ffprobe
RENDER_OUTPUT_WIDTH=1080
RENDER_OUTPUT_HEIGHT=1920
RENDER_FPS=30
```

---

## 4. Running the End-to-End Pipeline

### A. Local Dry-Run Mode (100% Offline, No API Keys Required)
Exercises the full user-facing pipeline using in-memory mock adapters without network calls or credentials:
```bash
python scripts/run_pipeline.py "The mystery of the Mariana Trench" --dry-run --output output/mariana-trench-dry --target-languages es fr
```

### B. Live Pipeline Mode (Requires API Credentials & FFmpeg)
Executes against live Claude, ElevenLabs, Pexels, and local FFmpeg:
```bash
python scripts/run_pipeline.py "The mystery of the Mariana Trench" --output output/mariana-trench --target-languages es fr
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

---

## 5. Run Directory Structure & Metadata

Every pipeline execution generates a self-contained output directory:

```
output/<run-dir>/
├── script/
│   ├── script.json         # Raw Script entity JSON metadata
│   └── script.txt          # Plain narration text
├── audio/
│   └── narration.mp3       # Generated voice audio track
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
├── video/
│   └── output.mp4          # Final vertical rendered MP4 video
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
| Asset Matching | Deterministic heuristic | Deterministic heuristic | None (In-process) |
| Timeline Assembly | Deterministic mapping | Deterministic mapping | None (In-process) |
| Video Rendering | `DryRunRenderProvider` | `FfmpegRenderProvider` | Local `ffmpeg` binary |
| Subtitle Generation | `SubtitleService` | `SubtitleService` | None (In-process) |
| Subtitle Translation | `DryRunTranslationProvider` | `ClaudeTranslationProvider` | `ANTHROPIC_API_KEY` |

### Common Failure Messages & Recovery:
- **`ProviderAuthError: API key is required`**: Missing credential in `.env`. Add key or run with `--dry-run`.
- **`ScriptGenerationError: Generated script has X words...`**: Model output violated spoken word count range. Re-run or adjust `--duration`.
- **`RenderError: ffmpeg binary not found`**: FFmpeg not installed on PATH. Install FFmpeg or run with `--dry-run`.
- **`SubtitleTranslationError: Cue count mismatch`**: Provider returned unexpected cue count during translation. Re-run or check model settings.

On any stage failure, `run_pipeline.py` logs the exact error to `run.log`, prints an actionable error message, writes partial `metadata.json` with status `"FAILED"`, and exits with code 1 without corrupting earlier stage outputs.

---

## 7. Running Tests & Validation

```bash
# Run full unit and performance test suite (213 tests)
pytest

# Run repository internal pipeline smoke test
python scripts/verify_pipeline.py
```
