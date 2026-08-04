# SELMA Labs — Operations & Developer Runbook

This runbook provides step-by-step instructions to set up, validate, test, and run the SELMA Labs Sprint 1–17 master codebase locally.

---

## 1. Prerequisites & Environment Setup

- **Python Version**: Python 3.10 or higher.
- **FFmpeg (Optional for Video Rendering)**: Ensure `ffmpeg` and `ffprobe` binaries are installed and accessible on your system `PATH`.
- **Usage Model**: This repository is a source repository designed to be run directly from its root.

```bash
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate
```

---

## 2. Dependency Installation

Install all required Python dependencies declared in `requirements.txt`:
```bash
pip install -r requirements.txt
```

Declared dependencies:
- `anthropic>=0.40.0`
- `pydantic-settings>=2.5.0`
- `pytest>=8.0.0`
- `pytest-asyncio>=0.24.0`
- `httpx>=0.27.0`
- `mutagen>=1.47.0`

---

## 3. Environment Variables Configuration

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

*Note: All 210 unit and performance tests run fully offline using fake/mock adapters without requiring live credentials.*

---

## 4. Running Tests

Execute the complete test suite (210 tests across unit and performance suites):
```bash
pytest
```

To run test collection only:
```bash
pytest --collect-only
```

---

## 5. Offline Pipeline Smoke Test

Run the permanent repository smoke test from the project root:
```bash
python scripts/verify_pipeline.py
```
This verifies `ScriptService` -> `VoiceService` -> `ScenePlanningService` -> `SceneAssetMatchingService` -> `TimelineService` -> `SubtitleService` using in-memory/fake providers.

---

## 6. CLI Commands Execution

All capabilities are accessible via CLI entry points under `scripts/`.

### Display Help Output for All Commands
```bash
python scripts/generate_script_test.py --help
python scripts/generate_voice.py --help
python scripts/search_assets.py --help
python scripts/plan_scenes.py --help
python scripts/match_assets.py --help
python scripts/create_timeline.py --help
python scripts/render_video.py --help
python scripts/generate_subtitles.py --help
python scripts/translate_subtitles.py --help
```

### Running Pipeline Scripts Live (Requires API Keys)
```bash
# Generate Script
python scripts/generate_script_test.py "The History of Quantum Computing"

# Generate Voice Narration
python scripts/generate_voice.py "The History of Quantum Computing"

# Build Video Timeline
python scripts/create_timeline.py "The History of Quantum Computing"

# Render Full Video with Subtitles
python scripts/render_video.py "The History of Quantum Computing" --subtitle

# Translate Subtitles
python scripts/translate_subtitles.py --track-id "sub-1" --target-languages es fr de
```
