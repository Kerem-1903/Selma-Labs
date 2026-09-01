# SELMA Labs

## Unified Local Factory

`scripts/run_factory.py` is the single production composition root. It accepts
either a topic or a licensed local MP3/WAV and persists every completed stage in
`.selma_runs/` so failed work can resume without repeating paid operations.
Every production invocation now runs a secret-free local preflight before
constructing paid providers. Missing tools, credentials, writable storage,
portrait settings, disk space, or an explicitly enabled Vision quality gate
stop the run before API quota is spent.

Topic mode runs script generation, source retrieval, strict claim verification,
source-grounded rewrite when required, directed narration, full-audio
adaptation, WhisperX word alignment, 2-5 word karaoke cue partitioning, visual
planning, vision-scored asset search, and a single-pass FFmpeg render in one
stage graph. An unsupported final fact report blocks the run before voice,
visual-search, or render costs are incurred. A successful topic run also performs
black/freeze/silence/loudness QA and produces a complete YouTube upload package.
For narrated videos, WhisperX force-aligns the approved script itself; when a
language is supplied, a second ASR transcription cannot silently replace words.
Audio mode joins the same graph at audio intelligence and uses the identical
alignment, subtitle, visual, and render policies.

```powershell
python scripts/system_health.py --profile factory
python scripts/run_factory.py --audio-path .\sarki.mp3
python scripts/run_factory.py --topic "Ahtapotların neden üç kalbi var?" --language tr --duration-seconds 30
python scripts/run_factory.py --topic "Derin okyanus" --language tr --music-theme mystery
python scripts/run_factory.py --topic "Derin okyanus" --no-background-music
python scripts/run_factory.py --audio-path .\sarki.mp3 --run-id <UUID>
python scripts/run_factory.py --topic "Ahtapot" --run-id <UUID> --additional-retries 2
python scripts/run_factory.py --topic "Ahtapot" --run-id <UUID> --reprocess-from VISION_SEARCH
```

`VISION_ENABLED=true` is an explicit production switch. Leave it disabled
until the configured Vision provider and budget are ready; the strict factory
will fail closed instead of silently calling a paid provider or bypassing visual
relevance checks. Use `--profile audio` for licensed-audio runs and
`--profile trends` for topic-discovery checks.

Both modes require Pexels and the configured Vision provider plus local FFmpeg
and WhisperX. Topic mode additionally requires the configured script provider
and ElevenLabs. `scripts/run_pipeline.py` is a compatibility alias to the same
factory; it contains no independent production implementation. See
[`docs/LOCAL_FACTORY_RELEASE_NOTES.md`](../LOCAL_FACTORY_RELEASE_NOTES.md)
for architecture, guarantees, quality gates, and operating constraints.

## Current Operational Pipeline

The production renderer uses one FFmpeg filter graph: bounded hard-cut visual
segments, Ken Burns motion, ASS burn-in, a speech-first studio mix at -14 LUFS,
BT.709 color metadata, and one final H.264 High Profile CRF 17 encode. No lossy
CRF intermediate is generated. The first visual starts immediately without a
fade from black.

Premium captions keep a complete phrase of at most four words visible in white while the
currently spoken word becomes yellow and briefly scales vertically. Single-word
flash cues are rejected before render rather than silently degrading output.

Visual planning produces a gap-free, time-coded storyboard rather than a flat
list of stock queries. The opening uses an approximately 1.2-second hook beat,
the first six seconds keep a denser rhythm, and later cuts remain at or below
the configured 2.8-second visual-beat budget.
Every beat carries a narrative role, varied shot type, supporting concepts,
energy-aware camera motion, and an exact render duration. Non-English concepts are
localized to concise, topic-anchored English stock queries. Thumbnail preflight and
AI Vision reject low-confidence or forbidden people/face, vehicle, text, logo, and
watermark conflicts. Selection prefers fresh footage, then non-adjacent verified
reuse, and only then a different phase of the same verified source—without lowering
the confidence gate.

After rendering, FFmpeg-based content QA checks opening/total black, freezes,
adaptive silence, integrated loudness, loudness range, true peak, clipping,
leading/trailing silence, stereo layout, sample rate, and measured AAC bitrate.
The dedicated audio gate requires at least 90/100 before packaging. Topic runs then create a sibling
`<run-id>_youtube/` directory containing `youtube_short.mp4`, localized SRT captions,
`youtube_metadata.json`, a rights-aware quality report, upload checklist, and a
thumbnail-selection frame.

Narrated topic videos automatically select a licensed local music bed when the
music manifest is available. A time-coded sound-design plan controls semantic
hook/mechanism/reveal/payoff effects, a subtle ambience layer, music intensity,
speech-driven ducking, collision spacing, limiting, and -14 LUFS mastering.
Procedural effects and ambience are generated locally. Music requires commercial
YouTube rights, source evidence, and a matching SHA-256 checksum; missing or
invalid evidence never triggers unlicensed use. See
[`docs/AUDIO_STUDIO_SYSTEM.md`](../AUDIO_STUDIO_SYSTEM.md).

Visual planning now has its own 90-point release gate. It plans shot scale,
motion, sparse semantic transitions, pattern interrupts, explanatory overlays,
and mobile safe zones; then verifies source diversity, rights, resolution,
rendered scene changes, longest visual stasis, and freeze evidence before the
upload package can pass. The free FFmpeg/Remotion/Pexels stack, reference render,
and paid future roadmap are documented in
[`docs/VISUAL_EDIT_STUDIO_SYSTEM.md`](../VISUAL_EDIT_STUDIO_SYSTEM.md).

## Sprint 1: Script Generation

Status: **complete and passing.**

## What was built

- `core/domain/entities/script.py` — the `Script` entity
- `core/domain/ports/script_generator_port.py` — the `ScriptGeneratorPort` interface
- `core/domain/exceptions.py` — typed exception hierarchy (Sprint 1 subset)
- `core/application/services/script_service.py` — `ScriptService`: input validation +
  output validation (word-count sanity check against target duration)
- `infrastructure/providers/script/claude_script_provider.py` — the Claude adapter,
  the only file that imports the Anthropic SDK
- `config/settings.py` — environment-driven configuration
- `scripts/generate_script_test.py` — CLI entrypoint (the composition root for this sprint)
- `tests/unit/test_script_service.py` — 7 unit tests against a fake provider, no network needed

## Installation

Requires Python 3.10+.

```bash
cd selma-labs
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Then set up your API key:

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

## Running the automated tests

These do **not** call the Anthropic API or need an API key — they test `ScriptService`'s
business logic against an in-memory fake provider. This is the payoff of coding against
`ScriptGeneratorPort`: the core logic is fully testable without touching the network.

```bash
python3 -m pytest tests/unit/ -v
```

Expected output: `7 passed`.

## Running it for real (generates an actual script via Claude)

```bash
python3 scripts/generate_script_test.py "Why did the Roman Empire collapse?"
```

Optional duration override (15–90 seconds):

```bash
python3 scripts/generate_script_test.py "The physics of black holes" --duration 60
```

### Expected output

```
============================================================
Topic:            Why did the Roman Empire collapse?
Target duration:  45s
Word count:       ~105-120
Provider:         anthropic:claude-sonnet-4-5
Script ID:        <uuid>
============================================================
<narration text — no markdown, no stage directions, ready for text-to-speech>
============================================================
```

If word count is far outside the expected range for the requested duration, or the script
is empty, the command exits with status 1 and a clear error message instead of printing
bad output — that's `ScriptService`'s output validation catching it.

## What "done" means for this sprint

Before moving to Sprint 2, run the CLI on at least 10 varied real topics (history, science,
"how X works", biography, controversy) and read every output. You're checking for:

- Does it actually hook you in the first sentence?
- Are the facts plausible and not obviously fabricated? (Spot-check a couple — LLMs can
  still state incorrect "facts" confidently. `ScriptService` cannot catch this; only your
  own judgment can, for now.)
- Is the pacing right for the target duration once you read it aloud at a natural pace?
- Does it consistently avoid stage directions/markdown creeping into the output?

If most of the 10 pass that bar, script generation is validated — move to Sprint 2
(Voice Generation). If not, this is the cheapest point in the whole roadmap to iterate on
the system prompt in `claude_script_provider.py` — do that before building anything
downstream of it.

## Design notes (why it's built this way)

- **Research is folded into script generation** for this sprint rather than being a
  separate `ResearchPort`/service — see the Sprint 1 kickoff discussion for the reasoning.
  If research quality becomes the bottleneck later, it becomes its own port without
  changing `ScriptService`'s public contract.
- **Word-count validation lives in `ScriptService`, not the adapter** — it's a business
  rule that must apply no matter which provider generated the text; putting it in the
  adapter would mean re-implementing it for every future provider (OpenAI, a fine-tuned
  model, etc.).
- **No database, no API, no queue** — per the MVP plan, this sprint runs entirely as a
  CLI script. Nothing here will need to be rewritten when those are added later; they'll
  simply call `ScriptService` the same way `generate_script_test.py` does now.

---

## Sprint 2: Voice Generation

Status: **complete and passing.**

### What was built

- `core/domain/entities/voice_track.py` — the `VoiceTrack` entity (final, persisted output)
- `core/domain/value_objects/generated_audio.py` — `GeneratedAudio` (raw adapter output, pre-storage)
- `core/domain/value_objects/storage_reference.py` — `StorageReference`
- `core/domain/ports/voice_generator_port.py` — `VoiceGeneratorPort` interface
- `core/domain/ports/storage_port.py` — `StoragePort` interface (named in Architecture v1, first implemented here)
- `core/domain/exceptions.py` — extended with `ProviderConnectionError`, `InvalidVoiceConfigurationError`, `VoiceGenerationError`, `StorageError`
- `core/application/services/voice_service.py` — `VoiceService`: validates input/output, orchestrates provider + storage
- `infrastructure/providers/voice/elevenlabs_provider.py` — the ElevenLabs adapter, the only file that knows the ElevenLabs API exists
- `infrastructure/storage/local_fs_storage.py` — the `StoragePort` adapter for the local filesystem
- `config/provider_registry.py` — config-driven provider selection (the one file that changes to add/swap a provider)
- `config/settings.py` — extended with voice/storage config
- `scripts/generate_voice.py` — CLI entrypoint (composition root for this sprint)
- `tests/unit/test_voice_service.py`, `tests/unit/test_local_fs_storage.py` — 12 new unit tests, no network required

### Configuring providers

Voice provider selection is entirely config-driven, via `.env`:

```bash
VOICE_PROVIDER=elevenlabs          # currently the only supported value
ELEVENLABS_API_KEY=sk_...
ELEVENLABS_MODEL_ID=eleven_multilingual_v2   # optional, this is the default
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb     # optional — "George", free-tier API compatible
STORAGE_ROOT_DIR=output            # optional, local folder audio files are written under
```

`config/provider_registry.py`'s `get_voice_provider()` reads `settings.voice_provider` and
returns the matching adapter — no other file needs to know which provider is active.

### Adding a new provider (e.g. OpenAI TTS, Azure Speech, a local model)

1. Implement `VoiceGeneratorPort` in a new file, e.g.
   `infrastructure/providers/voice/openai_tts_provider.py`. It must implement
   `async def generate_voice(self, text: str, voice_name: str) -> GeneratedAudio`, mapping
   that provider's errors onto the typed exceptions in `core/domain/exceptions.py`
   (`ProviderAuthError`, `ProviderTimeoutError`, `ProviderConnectionError`,
   `ProviderQuotaExceededError`, `InvalidVoiceConfigurationError`).
2. Add a branch for it in `config/provider_registry.py::get_voice_provider()`.
3. Add the new value to `Settings.voice_provider`'s `Literal[...]` type in `config/settings.py`,
   and any provider-specific config fields it needs (e.g. `openai_api_key`).
4. Set `VOICE_PROVIDER=openai` in `.env`.

`VoiceService`, its tests, and the CLI do not change at all.

### Running the automated tests

No network or API keys required — `test_voice_service.py` uses in-memory fakes for both
`VoiceGeneratorPort` and `StoragePort`; `test_local_fs_storage.py` writes to a pytest
temp directory.

```bash
python3 -m pytest tests/unit/ -v
```

Expected output: `19 passed` (7 from Sprint 1 + 12 new).

### Running it for real (generates actual narrated audio via ElevenLabs)

Set `ELEVENLABS_API_KEY` in `.env` (see above), then:

```bash
# Full pipeline: topic -> script (NVIDIA) -> narrated audio (ElevenLabs)
python3 scripts/generate_voice.py "Titanic"

# Voice-only: narrate raw text directly, skipping script generation
# (only needs ELEVENLABS_API_KEY, not ANTHROPIC_API_KEY)
python3 scripts/generate_voice.py --text "The Titanic sank in 1912."

# Override the voice for one run
python3 scripts/generate_voice.py "Titanic" --voice-id <some-other-voice-id>
```

### Expected output

```
============================================================
Audio ID:      <uuid>
Duration:      44.8s
Provider:      elevenlabs:eleven_multilingual_v2
Voice used:    JBFqnCBsd6RMkjVDRZzb
Sample rate:   44100 Hz
File path:     /absolute/path/to/output/voice/<script_id>-<uuid>.mp3
============================================================
```

Play the resulting `.mp3` and confirm: does it sound natural when read aloud, does the
pacing match the script, is there any audible artifacting? That's the manual quality bar
for this sprint, same spirit as Sprint 1's script review checklist.

### Design notes (why it's built this way)

- **`StoragePort` was already named in Architecture v1**, unimplemented until now because
  Sprint 1 had no binary output. Implementing it here is not a new architectural concept —
  see the Architecture Addendum discussion for how the team distinguishes "the architecture
  already accounted for this" from "this is scope creep."
- **`GeneratedAudio` vs `VoiceTrack`**: the adapter returns only what the TTS API itself
  produced; `VoiceService` is responsible for persistence and identity. This keeps every
  future voice provider adapter ignorant of storage entirely.
- **httpx directly, not the `elevenlabs` SDK**: keeps error-to-exception mapping fully
  under this codebase's control rather than depending on how a third-party SDK wraps errors.
- **`anthropic_api_key` became optional** in `config/settings.py` this sprint — now that
  `Settings` spans multiple providers, requiring every key up front just to run a
  voice-only test was the wrong default. Each adapter still fails fast with a clear typed
  error at construction time if its specific key is missing.

### Known limitation carried forward

Same as Sprint 1: I could not perform a live end-to-end synthesis call against the real
ElevenLabs API in the environment used to build this (no key, and the sandbox's network
egress doesn't include `api.elevenlabs.io`). The full test suite (19 tests) passes, and
both CLI error paths were verified to fail cleanly with typed errors rather than raw
tracebacks — but a live run with your own `ELEVENLABS_API_KEY` is the last verification
step before calling this sprint done, same as the manual script-quality review was for
Sprint 1.

---

## Sprint 2.1: Speech Timing Support + Transparent Audio Caching

Status: **complete and passing.** Non-breaking addition on top of Sprint 2 — no existing
file's public behavior changed, only extended.

### What was built

- `core/domain/value_objects/speech_segment.py` — `SpeechSegment` (text, start, end)
- `GeneratedAudio` and `VoiceTrack` — extended with an optional `segments: list[SpeechSegment]`
  field, defaulting to `[]`. Fully backward compatible: any code written against the Sprint 2
  shape of these classes keeps working unmodified.
- `VoiceTrack.to_dict()` — exports the `{audio_file, duration, segments}` shape for downstream
  consumers (e.g. a future Sprint 3 Scene Planner).
- `infrastructure/providers/voice/caching_voice_provider.py` — `CachingVoiceProvider`, a
  `VoiceGeneratorPort` **decorator** that transparently caches generated audio by
  `SHA256(provider_identity | voice_name | script_text)`.
- `config/provider_registry.py` — updated to wrap the base provider in `CachingVoiceProvider`
  when `VOICE_CACHE_ENABLED=true` (default).
- 12 new unit tests (`test_caching_voice_provider.py` + additions to `test_voice_service.py`)

### Why a decorator, not a change to VoiceService

The requirement was that caching be transparent to the application layer. `VoiceService` is
constructed with a `VoiceGeneratorPort` and has no way to know — or need to know — whether
that instance talks to ElevenLabs directly or is wrapped in a cache first. Whether caching is
active is decided entirely in `config/provider_registry.py`, the composition point. This also
means the cache can be disabled for a single run without touching any service code.

No separate `CachePort` abstraction was introduced. Caching here is an internal optimization
of one decorator, not a capability anything else in the system needs to plug into or swap
independently — if that changes later (e.g. a shared cache across multiple workers), extracting
a `CachePort` at that point is a small, contained change, same reasoning applied to other
YAGNI calls in Architecture v1.

### Speech timing status

`ElevenLabsVoiceProvider` currently returns `segments=[]` — the base REST call used doesn't
request timing data. The domain model (`GeneratedAudio`, `VoiceTrack`) fully supports it now;
wiring in ElevenLabs' timestamp-returning endpoint variant later is a contained change to that
one adapter file, with zero changes needed to `VoiceGeneratorPort`, `VoiceService`, or anything
that consumes a `VoiceTrack`.

### Configuring the cache

```bash
VOICE_CACHE_ENABLED=true       # default; set false to always call the provider
VOICE_CACHE_DIR=cache/voice    # default; local folder cached audio + metadata live under
```

### Testing

```bash
python3 -m pytest tests/unit/ -v
```

Expected output: `28 passed` (19 from Sprint 1+2, 9 new from 2.1).

### Trying the cache manually

```bash
# First run: calls ElevenLabs, writes to cache/voice/
python3 scripts/generate_voice.py --text "The Titanic sank in 1912."

# Second run with identical text + voice: served from cache, no API call
python3 scripts/generate_voice.py --text "The Titanic sank in 1912."

# See the structured JSON shape (audio_file, duration, segments)
python3 scripts/generate_voice.py --text "The Titanic sank in 1912." --json
```

---

## Sprint 3: Visual Asset Discovery

Status: **complete and passing.**

### What was built

- `core/domain/entities/media_asset.py` — the `MediaAsset` entity: a
  provider-independent representation of one discovered visual asset
  (id, provider, media_type, dimensions, duration, fps, tags, attribution,
  license, local_path, optional score). No Pexels-specific (or future
  Pixabay/Mixkit-specific) response object is ever allowed to reach the
  application layer — every adapter must translate into this shape first.
- `core/domain/ports/video_source_port.py` — `VideoSourcePort`: `search()`
  queries a provider's catalog, `download()` fetches one asset's raw bytes.
  Both live on the Port because both are provider-specific enough that the
  application layer must not assume how they work.
- `core/domain/exceptions.py` — extended with `VideoSearchError` (invalid
  query/max_results, or zero results for a valid query) and
  `AssetDownloadError` (a selected asset's content failed to download or
  was empty — distinct from `StorageError`, which covers failures
  persisting bytes already downloaded).
- `core/application/services/video_search_service.py` —
  `VideoSearchService`: validates input, searches via the injected
  `VideoSourcePort`, validates the result set isn't empty, downloads every
  returned asset, and persists each one via the injected `StoragePort`.
  Same shape as `ScriptService`/`VoiceService`: depends only on Ports,
  never on a concrete provider or storage backend.
- `infrastructure/providers/video/pexels_provider.py` — `PexelsProvider`,
  the only file in the codebase that knows the Pexels API exists or what
  its response JSON looks like. Uses `httpx` directly (same reasoning as
  `ElevenLabsVoiceProvider`: full control over error-to-exception mapping).
- `config/provider_registry.py` — extended with `get_video_source_provider()`,
  same config-driven pattern as `get_voice_provider()`.
- `config/settings.py` — extended with `video_provider`, `pexels_api_key`,
  `default_video_max_results`.
- `scripts/search_assets.py` — CLI entrypoint (composition root for this
  sprint).
- `tests/unit/test_video_search_service.py`,
  `tests/unit/test_pexels_provider.py` — 20 new unit tests, no network
  required.

### Scope, deliberately

Per the sprint brief: **no semantic ranking, no scene matching, no AI
selection.** "Selected assets" for this sprint means every asset the
provider returned (bounded by `max_results`) — `VideoSearchService`
downloads and persists all of them. Narrowing that set down by relevance is
a later sprint's job, built on top of this service without changing its
public contract (the same reasoning `VoiceService` used for caching:
extend at the composition/adapter boundary, not by reshaping the service
that already works).

Only one provider — Pexels — is implemented. Adding Pixabay, Mixkit, or any
other provider later follows the exact three-step pattern already
documented for voice providers above: implement `VideoSourcePort`, add a
branch in `config/provider_registry.py::get_video_source_provider()`, add
the new value to `Settings.video_provider`'s `Literal[...]`.

### Why download() lives on the Port, not in VideoSearchService

Fetching an asset's bytes looks like "just an HTTP GET," but the Port
exists to protect the application layer from ever assuming that. Some
providers serve plain public file URLs (Pexels does); others require
signed URLs, extra headers, or a completely different retrieval mechanism.
Keeping `download()` on `VideoSourcePort` means `VideoSearchService` stays
provider-agnostic even though, for Pexels specifically, the implementation
today is a plain GET.

### Configuring the provider

```bash
VIDEO_PROVIDER=pexels              # currently the only supported value
PEXELS_API_KEY=your-pexels-api-key-here
DEFAULT_VIDEO_MAX_RESULTS=10       # optional, this is the default
```

Downloaded video files are persisted through the same `StoragePort` /
`LocalFsStorage` used for voice audio, under `output/video/` (governed by
the existing `STORAGE_ROOT_DIR` setting) — no new storage concept was
introduced.

### Testing

```bash
python3 -m pytest tests/unit/ -v
```

Expected output: `48 passed` (28 from Sprints 1-2.1, 20 new from Sprint 3).
`test_pexels_provider.py` tests the adapter's pure response-mapping and
status-code-to-exception logic directly (no network);
`test_video_search_service.py` tests `VideoSearchService` end-to-end
against fake `VideoSourcePort`/`StoragePort` implementations.

### Running it for real (searches Pexels and downloads actual video files)

Set `PEXELS_API_KEY` in `.env` (get one free at pexels.com/api), then:

```bash
python3 scripts/search_assets.py "Titanic ship"

# Limit how many assets to fetch
python3 scripts/search_assets.py "Titanic ship" --max-results 5

# Structured JSON output (one object per MediaAsset)
python3 scripts/search_assets.py "Titanic ship" --json
```

### Expected output

```
============================================================
Query:        Titanic ship
Assets found: 10
============================================================
ID:          pexels:2499611
Provider:    pexels
Dimensions:  1080x1920 @ 25.0 fps
Duration:    10.0s
Tags:        Titanic ship
Attribution: Video by Ruvim Miksanskiy on Pexels
License:     Pexels License (https://www.pexels.com/license/)
Local path:  /absolute/path/to/output/video/pexels-2499611.mp4
------------------------------------------------------------
...
```

If the query returns nothing, or the provided `PEXELS_API_KEY` is
missing/invalid, the command exits with status 1 and a clear error message
— that's `VideoSearchService`'s input/output validation and
`PexelsProvider`'s typed error mapping catching it, same pattern as every
prior sprint's CLI.

### Known limitation carried forward

Same as every prior sprint: I could not perform a live end-to-end search
and download against the real Pexels API in the environment used to build
this (no key, and the sandbox's network egress doesn't include
`api.pexels.com`). The full test suite (48 tests, all against fakes and
manually-constructed HTTP response objects) passes. A live run with your
own `PEXELS_API_KEY` — confirming assets actually download and play, and
that the "no results" and invalid-key paths fail cleanly against the real
API — is the last verification step before calling this sprint done, same
as the manual quality reviews were for Sprints 1 and 2.

### Design notes (why it's built this way)

- **`MediaAsset` is one entity, not a raw/final split like
  `GeneratedAudio`/`VoiceTrack`.** Voice generation needed that split
  because persistence adds genuinely new fields (`audio_id`, `file_path`)
  on top of what the provider returns. Here, the provider-independent shape
  and the persisted shape are the same fields — only `local_path` changes,
  from `None` to a real path — so a second class would be duplication
  without a matching reason, which is the same reasoning documented for
  not introducing a `CachePort` in Sprint 2.1.
- **Tags fall back to the search query when a provider doesn't supply
  them.** Pexels' video objects usually carry an empty `tags` list; rather
  than surface an empty list, the query itself ("what was this found
  with") is preserved as the tag — small detail, but relevant metadata for
  a future scene-matching sprint that needs to know why an asset was
  chosen.
- **No selection/ranking logic in `VideoSearchService`.** Every returned
  asset is downloaded. This is exactly what the sprint brief asked for —
  building a scoring step now, ahead of the sprint that actually needs it,
  would be exactly the kind of premature abstraction the MVP plan warns
  against.

### Future enhancements (deliberately not built yet)

- **Split `VideoSourcePort` into `VideoSourcePort.search()` and a separate
  `AssetDownloaderPort.download()`.** Today both live on one Port. That's
  fine while every provider fetches its files the same simple way (a plain
  authenticated GET). It stops being fine once a provider's download
  mechanics genuinely diverge from its search mechanics — e.g. Google
  Drive or S3 as asset sources, where "download" means something
  structurally different from "search a catalog." At that point the split
  is a small, contained change (extract the method, adjust
  `provider_registry.py`) — not a reason to build it pre-emptively now,
  same reasoning as every other YAGNI call already documented in this
  README. Noted here so it isn't forgotten, not scheduled.

---

## Sprint 3.1: MediaAsset Identity + Metadata Extension

Status: **complete and passing.** Non-breaking addition on top of Sprint 3,
same spirit as Sprint 2.1 was to Sprint 2 — one existing file's shape grew,
nothing that already worked stopped working.

### What was built

- `MediaAsset` — extended with:
  - `provider_asset_id: str` — the raw, provider-native id with no prefix
    (e.g. `"2499611"`), distinct from `id` (`"pexels:2499611"`), which
    stays the globally-unique, collision-safe identifier used everywhere
    else in the codebase. `provider_asset_id` is what a provider's own API
    expects back if an asset ever needs to be re-fetched, deep-linked, or
    compared against that provider's native records.
  - `metadata: dict[str, Any]` — an open, empty-by-default bag reserved
    for attributes no provider search API returns today but a later AI
    Vision analysis step could compute per-asset (e.g. `dominant_colors`,
    `motion_level`, `people_count`, `indoor_outdoor`, `camera_angle`,
    `detected_objects`). Nothing in this sprint populates or reads it —
    it exists purely so a future Scene Planning/matching sprint has
    somewhere to put that data without another MediaAsset shape change.
- `PexelsProvider._map_video` — now sets `provider_asset_id` from the raw
  Pexels numeric id; `metadata` is left at its default `{}`.
- `VideoSearchService._build_storage_key` — simplified to read
  `asset.provider_asset_id` directly instead of string-splitting `asset.id`.
- Tests extended in both `test_video_search_service.py` and
  `test_pexels_provider.py` to cover the new fields.

### Note on backward compatibility

Unlike Sprint 2.1's `segments` field (optional, defaulted to `[]`),
`provider_asset_id` was added as a **required** field, not an optional one
with a default. It's core identity information, not an incremental
capability — a `MediaAsset` without it is missing something every provider
adapter can and should supply, so there's no meaningful default to fall
back to. Since `MediaAsset` had exactly one production call site
(`PexelsProvider._map_video`) at the time of this change, this is a
same-sprint refinement rather than a compatibility break affecting
downstream consumers. `metadata` follows the Sprint 2.1 pattern exactly
(optional, defaulted, purely additive).

### Testing

```bash
python3 -m pytest tests/unit/ -v
```

Expected output: `48 passed` (test count unchanged from Sprint 3 — this was
a field-level refinement, not new test scenarios beyond the two added
assertions per existing test file).

---

## Sprint 4: Scene Planning

Status: **complete and passing.**

### What was built

- `core/domain/value_objects/scene.py` — `Scene`: a value object, not an
  entity (same relationship to `ScenePlan` that `SpeechSegment` has to
  `VoiceTrack` — no identity of its own, `index` is just positional
  bookkeeping). Fields: `index`, `narration`, `search_keywords`,
  `detected_objects`, `location`, `mood`, `visual_priority`, plus
  `start_time`/`end_time` defaulting to `0.0`. One class, not a raw/final
  pair — same reasoning documented for `MediaAsset` in Sprint 3.1: nothing
  except timing changes between "just produced by the provider" and
  "final," so a second class would be duplication without a matching
  reason.
- `core/domain/entities/scene_plan.py` — `ScenePlan`: the entity result of
  planning one Script/VoiceTrack pair (own `uuid`, `script_id`,
  `voice_track_id`, `total_duration_seconds`, `provider_used`, ordered
  `scenes`, `created_at`). Same shape and role as `Script`/`VoiceTrack`.
- `core/domain/ports/scene_planning_port.py` — `ScenePlanningPort`: one
  method, `plan_scenes(narration_text) -> list[Scene]`, plus a
  `provider_identity` property (mirrors how `Script.provider_used` and
  `VoiceTrack.provider` track provenance — added here as a Port-level
  contract since, unlike Script/VoiceTrack, nothing else on this Port's
  raw output carries that information). Confirmed genuinely required by
  the architecture, not built defensively: scene planning is an
  AI-provider-backed capability exactly like script generation and voice
  generation, both already hidden behind a Port — omitting one here would
  be the actual architecture violation.
- `core/domain/exceptions.py` — extended with `ScenePlanningError`, playing
  the same dual role `ScriptGenerationError` already plays: invalid input
  (empty narration, invalid voice track duration) *and* invalid provider
  output (empty scene list, a scene missing narration/keywords, or a raw
  response that couldn't even be parsed as JSON).
- `core/application/services/scene_planning_service.py` —
  `ScenePlanningService`: validates input, calls the provider, validates
  the returned scenes, then computes each scene's `start_time`/`end_time`.
  Depends only on `ScenePlanningPort` — never on a concrete provider.
- `infrastructure/providers/scene_planning/claude_scene_planning_provider.py`
  — `ClaudeScenePlanningProvider`, the only file that knows how this
  codebase prompts Claude for scene planning or what JSON shape it expects
  back. Same adapter discipline as `ClaudeScriptProvider`: typed exception
  mapping for auth/timeout/quota/connection failures, no prompt logic
  anywhere else.
- `config/settings.py` / `config/provider_registry.py` — extended with
  `scene_planning_provider`, `scene_planner_model`, and
  `get_scene_planning_provider()`, the same config-switch pattern as every
  other provider category.
- `scripts/plan_scenes.py` — CLI entrypoint (composition root for this
  sprint), with a full-pipeline mode (topic → script → voice → scene plan)
  and a narration-only `--text` mode for testing scene planning without
  needing an ElevenLabs key.
- `tests/unit/test_scene_planning_service.py` (11 tests),
  `tests/unit/test_claude_scene_planning_provider.py` (15 tests) — 26 new
  unit tests, no network or API key required.

### Why timing is computed by the service, not asked of the provider

This is the one deliberate deviation from "the provider does the AI work,
the service validates it," and it's worth calling out explicitly. An LLM
has no reliable internal sense of elapsed seconds — asking Claude to
invent `start_time`/`end_time` values would just be manufacturing false
precision. `VoiceTrack.duration_seconds`, on the other hand, is a real,
measured value: `VoiceService` already refuses to construct a `VoiceTrack`
with a duration `<= 0`. So `ScenePlanningPort.plan_scenes()` returns scenes
with untouched `0.0` timing, and `ScenePlanningService` allocates the
measured total duration across scenes proportionally to each scene's share
of the narration's word count — snapping the final scene's `end_time`
exactly to the total duration so proportional rounding can't drift short
or long across many scenes.

This is also the literal answer to the brief's "if `SpeechSegment` timing
is unavailable, the planner should still work by estimating scene timing
from narration": no voice provider in this codebase populates
`VoiceTrack.segments` yet (`ElevenLabsVoiceProvider` always returns
`segments=[]`, per Sprint 2's known limitation) — so proportional
estimation from word count isn't a fallback path, it's the *only* path
today, and Scene Planning had to work without depending on timing data
that doesn't exist yet.

### Configuring the provider

```bash
SCENE_PLANNING_PROVIDER=claude          # currently the only supported value
SCENE_PLANNER_MODEL=claude-sonnet-4-5   # optional, this is the default
```

Reuses `ANTHROPIC_API_KEY` — same Anthropic account as script generation, a
separate model setting because scene planning's prompt and output shape
are different enough from script generation that tuning one shouldn't be
forced to also affect the other.

### Testing

```bash
python3 -m pytest tests/unit/ -v
```

Expected output: `74 passed` (48 from Sprints 1-3.1, 26 new). Edge cases
covered per the sprint brief: empty narration, a single-scene narration, a
multi-scene narration with proportional timing, an invalid voice track
duration, and several shapes of malformed provider output (invalid JSON,
valid JSON that isn't a list, a scene missing `narration`, a scene with no
`search_keywords`, a non-object array element).

### Running it for real

```bash
# Full pipeline: needs ANTHROPIC_API_KEY and ELEVENLABS_API_KEY
python3 scripts/plan_scenes.py "Titanic"

# Narration-only: needs only ANTHROPIC_API_KEY
python3 scripts/plan_scenes.py --text "The Titanic left Southampton in 1912. It struck an iceberg at night and sank."

# Structured JSON output (full ScenePlan, matching ScenePlan.to_dict())
python3 scripts/plan_scenes.py "Titanic" --json
```

### Expected output

```
============================================================
Total duration: 45.0s
Scenes:         3
============================================================
Scene 1
00:00–00:14
Narration: The Titanic was the largest ship of its time, a marvel of engineering set to cross the Atlantic.
Keywords:
  titanic ship
  ocean liner
  departure harbor
Objects:
  ship
  passengers
Location: harbor
Mood: hope
Visual priority: high
------------------------------------------------------------
Scene 2
00:14–00:31
...
```

If the narration is empty, the voice track has an invalid duration, or the
Claude response can't be parsed into scenes, the command exits with status
1 and a clear error message — `ScenePlanningService`'s validation and
`ClaudeScenePlanningProvider`'s typed error mapping catching it, same
pattern as every prior sprint's CLI.

### Known limitation carried forward

Same as every prior sprint that calls a real external API: I could not
perform a live end-to-end scene-planning call against the real Anthropic
API in the environment used to build this (no key, no network egress to
`api.anthropic.com` in this sandbox). The full test suite (74 tests, all
against fakes and hand-constructed JSON/response text) passes, and the
service-layer timing/validation logic was additionally verified by hand
end-to-end against a stubbed Anthropic SDK. A live run with your own
`ANTHROPIC_API_KEY` is the last verification step before calling this
sprint done, same as for every other AI-provider-backed sprint so far.

### Design notes (why it's built this way)

- **`Scene` is one class, not a raw/final split.** Directly following the
  precedent set for `MediaAsset` in Sprint 3.1: the only field that
  changes after the provider returns a scene is timing, so a second class
  would be duplication without a matching reason.
- **`ScenePlanningService` re-derives each scene's `index` from list
  order**, rather than trusting an index a provider might echo back in
  its JSON. Cheap defensive validation against a provider response with
  gaps or duplicate indices — covered by
  `test_scenes_are_reindexed_regardless_of_provider_supplied_index`.
- **`visual_priority` is a plain `str`, not a `Literal`/enum**, because the
  *provider adapter* is responsible for normalizing whatever Claude
  returns into one of `"high"/"medium"/"low"` (falling back to `"medium"`
  for anything else) — the domain layer just carries the already-
  normalized value through, the same division of responsibility already
  used for `MediaAsset.media_type`.

### Future Enhancements (deliberately not built yet)

- **Use `VoiceTrack.segments` (real per-word timing) to align scene
  boundaries, once a voice provider actually populates it.** Today's
  proportional word-count estimation is the best available option because
  no provider populates `segments` yet (see Sprint 2's known limitation).
  The moment one does, `ScenePlanningService._assign_timing` becomes a
  contained, provider-independent change (prefer measured segment
  boundaries when available, fall back to proportional estimation when
  not) — not a reason to build a timing-alignment algorithm today against
  data that doesn't exist.
- **A `score`/confidence field on `Scene`, mirroring `MediaAsset.score`.**
  Sprint 3 deferred asset ranking; the symmetric idea here — Claude
  self-rating how confident it is in a scene's grouping or keywords — has
  no consumer yet and no defined scoring rubric. Adding the field now,
  unused, would be exactly the kind of premature plumbing this project's
  MVP philosophy warns against.
- **Cross-checking `Scene.detected_objects` against what a downloaded
  `MediaAsset` actually shows (AI Vision verification).** This is squarely
  a Sprint 6+ (Video Assembly / Quality Review) concern once actual video
  files are in hand — `MediaAsset.metadata` (added in Sprint 3.1) was
  already left open specifically to receive this kind of data later.
- **Enforcing a minimum/maximum scene count relative to
  `target_duration_seconds`** (e.g. rejecting a 90-second script planned
  as a single scene, or as twenty). The sprint brief explicitly asks the
  planner to avoid mechanically splitting every sentence and to group
  related ideas — adding a numeric scene-count guardrail on top would
  second-guess that same instruction without a concrete failure case
  driving it yet. Worth revisiting once real Claude output shows whether
  this is actually a problem in practice.

### Test count correction

The "74 passed" figure above (and the "48 from Sprints 1-3.1" it's built
from) understates the actual count — `test_pexels_provider.py` and
`test_video_search_service.py` carry more tests than that running total
credits them with. The correct count at the end of Sprint 4, confirmed by
running the suite directly, is **79 passed**, not 74. Left the original
numbers in place above rather than silently rewriting sprint history;
flagging the discrepancy here instead, found during a full architectural
review before Sprint 5 began.

---

## Sprint 5: Scene Asset Matching

Status: **complete and passing.**

### What was built

- `core/domain/value_objects/scene_asset_match.py` — `SceneAssetMatch`: a
  value object, not an entity — same relationship to `AssetMatchPlan` that
  `Scene` has to `ScenePlan`. Pairs one `Scene` (carried through in full,
  not just its index) with its ranked list of candidate `MediaAsset`s.
  `assets` may be empty — a `has_matches` property makes that check
  readable at call sites without repeating `len(assets) > 0` everywhere.
- `core/domain/entities/asset_match_plan.py` — `AssetMatchPlan`: the
  entity result of matching for one `ScenePlan` (own `uuid`,
  `scene_plan_id`, ordered `matches`, `created_at`). Same shape and role
  as `Script`/`VoiceTrack`/`ScenePlan`. References only `scene_plan_id` —
  its one direct parent — not `script_id`/`voice_track_id`, which are
  `ScenePlan`'s concern; a consumer that needs the full ancestry follows
  `AssetMatchPlan -> ScenePlan -> Script`/`VoiceTrack` rather than this
  entity duplicating ids it doesn't itself depend on.
- `core/domain/exceptions.py` — extended with `SceneAssetMatchingError`,
  deliberately narrower than `ScriptGenerationError`/`ScenePlanningError`'s
  dual role: it covers invalid input (a `ScenePlan` with no scenes) only.
  A single scene returning zero matching assets is explicitly **not**
  this exception — see "Why a scene with no matches isn't a failure"
  below.
- `core/application/services/scene_asset_matching_service.py` —
  `SceneAssetMatchingService`: for every `Scene` in a `ScenePlan`, builds
  a search query from that scene's `search_keywords`, searches for
  candidates via an injected `VideoSearchService`, ranks them with
  deterministic heuristics, and returns an `AssetMatchPlan`. Depends on
  `VideoSearchService` directly — see "Why this depends on a service, not
  a Port" below.
- `core/application/services/video_search_service.py` — extended with a
  new public method, `search()`, alongside the existing `discover()`.
  `discover()`'s behavior, signature, and tests are completely unchanged;
  both methods now share a private `_validate_and_search` helper for the
  query/max_results validation and the provider call, which is the only
  part of `discover()` that moved. `search()` returns candidates without
  downloading or persisting them, and — unlike `discover()` — does not
  raise when the provider returns zero results, since a per-scene caller
  needs to treat "no candidates for this query" as a normal outcome to
  record, not a failure.
- `scripts/match_assets.py` — CLI entrypoint (composition root for this
  sprint), with a full-pipeline mode (topic → script → voice → scene
  plan → matched assets) and a narration-only `--text` mode for testing
  matching with only an Anthropic key + a Pexels key, no ElevenLabs key
  needed.
- `tests/unit/test_scene_asset_matching_service.py` (13 tests),
  `tests/unit/test_video_search_service.py` (6 new tests for `search()`)
  — 19 new unit tests, no network or API key required.

### Why a scene with no matches isn't a failure

This is the one deliberate deviation from how every prior AI-provider-backed
sprint handles "the provider found nothing" — worth calling out explicitly,
same spirit as Sprint 4's timing note. `VideoSearchService.discover()`
still raises `VideoSearchError` when a *standalone* search returns zero
results, because for that caller, zero results **is** the whole outcome of
the call — there's nothing else to return. `SceneAssetMatchingService` is
different: it runs one search per scene, and one scene's keywords failing
to match a Pexels asset says nothing about whether the *other* scenes will
match. Failing the entire `AssetMatchPlan` because one scene out of ten
came back empty would throw away nine scenes' worth of good matches over
one bad one. So an empty candidate list for a scene is recorded on that
scene's `SceneAssetMatch` (`assets == []`, `has_matches == False`) and
matching continues — a business outcome for a future sprint to decide how
to recover from (broaden the query? fall back to a generic b-roll asset?
flag the scene for manual review?), not an error this sprint should
swallow silently or crash on.

Genuine provider failures (auth, timeout, connection, quota) are treated
completely differently and still propagate immediately, stopping the
remaining scenes from being processed — those aren't "no results," they're
"the request never actually completed," and retrying or surfacing them to
the caller is still the right move, same as every other sprint.

### Why this depends on a service, not a Port

`SceneAssetMatchingService` is constructed with a `VideoSearchService`
instance — a concrete application-layer class — rather than a Port. Every
other service in this codebase depends only on Ports; this is a
deliberate, narrow exception, evaluated explicitly before writing any code
rather than introduced by default. Query-building (joining a `Scene`'s
`search_keywords` into a query string) is a deterministic, in-process
transformation of data already inside the application — there is no
external system on the other side of it to hide behind a `QueryBuilderPort`.
Introducing one anyway would be exactly the kind of premature abstraction
this project's MVP philosophy already warns against elsewhere (see Sprint
2.1's reasoning for not introducing a `CachePort`, and Sprint 3's for not
splitting `VideoSourcePort.download()` pre-emptively). `VideoSourcePort`
and `StoragePort` stay fully swappable underneath this — `SceneAssetMatchingService`
never touches either directly, only through `VideoSearchService`, so
neither port's substitutability is compromised by this composition.

To make this concrete without duplicating any of `VideoSearchService`'s
validation or provider-call logic, `VideoSearchService` gained one new
public method, `search()` (see "What was built" above) — the search phase
of `discover()`, exposed on its own, with `discover()` itself completely
unchanged. This was evaluated as the cleanest option before being built:
the alternative (`SceneAssetMatchingService` calling `VideoSourcePort`
directly) would have meant re-implementing query/max_results validation a
second time, with no matching benefit.

### Ranking heuristics

Deliberately lightweight and fully deterministic — no embeddings, no CLIP,
no AI Vision, no semantic models; those stay Sprint 6+ concerns, same
distinction Sprint 3.1 already drew for `MediaAsset.metadata`. Each
candidate gets a plain numeric score, computed as a weighted sum of:

- **Keyword overlap** (dominant signal, weight 10.0 per matching keyword):
  case-insensitive, whole-token overlap between `scene.search_keywords`
  and `asset.tags`.
- **Portrait orientation** (weight 3.0, or 1.0 for exactly square): SELMA
  Shorts are vertical video, so an asset with `height > width` fits the
  target format without cropping and is preferred when other signals are
  equal. Landscape assets get no bonus, not a penalty — still usable, just
  not preferred.
- **Duration coverage** (weight 2.0, scaled): an asset at least as long as
  the scene it would cover (`scene.end_time - scene.start_time`) gets full
  credit; a shorter asset gets partial credit proportional to how much of
  the scene's duration it actually covers.

All three weights are named module-level constants in
`scene_asset_matching_service.py` — changing the balance between them is a
one-line, fully-inspectable edit, not a retrain. Candidates missing
dimensions or duration (e.g. a provider that doesn't report them) simply
skip that term rather than erroring or being penalized.

### Configuring

No new configuration. Scene Asset Matching reuses `VIDEO_PROVIDER`/
`PEXELS_API_KEY` from Sprint 3 (via the same `VideoSearchService` and
`get_video_source_provider()`) and `SCENE_PLANNING_PROVIDER`/
`ANTHROPIC_API_KEY` from Sprint 4 — no new provider category, so nothing
new needed in `config/settings.py` or `config/provider_registry.py`.

```bash
python3 scripts/match_assets.py "Titanic"

# Narration-only, needs only ANTHROPIC_API_KEY + PEXELS_API_KEY
python3 scripts/match_assets.py --text "The Titanic left Southampton in 1912. It struck an iceberg at night."

# Cap how many candidates are considered per scene before ranking (default 10)
python3 scripts/match_assets.py "Titanic" --candidates-per-scene 5

# Structured JSON output (full AssetMatchPlan, matching AssetMatchPlan.to_dict())
python3 scripts/match_assets.py "Titanic" --json
```

### Testing

```bash
python3 -m pytest tests/unit/ -v
```

Expected output: `98 passed` (79 from Sprints 1-4, 19 new: 13 for
`SceneAssetMatchingService` covering ordering, query-building,
no-download behavior, the empty-scene business outcome, continued
processing after an empty scene, provider-error propagation, and all
three ranking heuristics individually; 6 for `VideoSearchService.search()`
covering the same validation/error paths as `discover()` plus the
empty-result-does-not-raise behavior that's unique to `search()`).

### Running it for real

Set `ANTHROPIC_API_KEY` and `PEXELS_API_KEY` in `.env` (plus
`ELEVENLABS_API_KEY` for full-pipeline mode), then:

```bash
python3 scripts/match_assets.py "Titanic"
```

### Expected output

```
============================================================
Scenes:          3
Matched scenes:  2
Unmatched scenes: 1
============================================================
Scene 1
Narration: The Titanic was the largest ship of its time...
Keywords:  titanic ship, ocean liner, departure harbor
Assets:    4 candidate(s), best first
  1. pexels:2499611  1080x1920  10.0s  tags=['titanic ship']
  2. pexels:3184433  1920x1080  8.0s  tags=['ship', 'ocean']
  ...
------------------------------------------------------------
Scene 2
...
```

If the scene plan has no scenes, or a provider auth/timeout/quota failure
occurs during any scene's search, the command exits with status 1 and a
clear error message — `SceneAssetMatchingService`'s input validation and
the underlying `VideoSourcePort` adapter's typed error mapping catching
it, same pattern as every prior sprint's CLI. A scene with zero matching
candidates does **not** cause a non-zero exit — it's printed as "(none
found)" and the command still succeeds, per this sprint's core design
decision above.

### Known limitation carried forward

Same as every prior sprint that calls a real external API: I could not
perform a live end-to-end run against the real Anthropic/Pexels APIs in
the environment used to build this (no keys, no network egress to
`api.anthropic.com` or `api.pexels.com` in this sandbox). The full test
suite (98 tests, all against fakes) passes, and the CLI's error path was
verified to fail cleanly with a typed error rather than a raw traceback
when `ANTHROPIC_API_KEY` is missing. A live run with your own API keys —
confirming ranked candidates are actually sensible for a real scene plan,
not just internally consistent against fakes — is the last verification
step before calling this sprint done, same as every prior AI/API-backed
sprint.

### Design notes (why it's built this way)

- **`SceneAssetMatch` embeds the full `Scene`, not just its index.** Same
  reasoning `GeneratedAudio` uses for embedding full `SpeechSegment`
  objects rather than offsets: a consumer of one match never needs to
  reach back into a separate `ScenePlan` to know what it was matched
  against.
- **No new Port, no `provider_registry.py` changes.** Query-building is an
  internal, deterministic transformation — not a call to an external,
  swappable system — so there is nothing here that belongs behind a Port.
  See "Why this depends on a service, not a Port" above.
- **Matching never downloads.** `SceneAssetMatchingService` only calls
  `VideoSearchService.search()`, never `discover()` — ranking happens
  before any bytes are fetched, so a scene with ten ranked candidates
  costs the same one search call as a scene with two, regardless of how
  many candidates are ultimately worth downloading later. Actually
  downloading the selected asset per scene is Video Assembly's job.

### Future Enhancements (deliberately not built yet)

- **Selecting and downloading exactly one asset per scene.** This sprint
  ranks; it does not choose or fetch. Once Video Assembly (Sprint 6+)
  needs an actual file per scene, it can call `VideoSearchService.discover()`
  — or a smaller download-one-asset helper — on just the top-ranked
  candidate from each `SceneAssetMatch`, without any change to
  `SceneAssetMatchingService`'s public contract.
- **Recovering from an unmatched scene** — broadening the query, falling
  back to a generic b-roll category, or flagging the scene for manual
  review. `SceneAssetMatch.has_matches` exists specifically so a later
  sprint has a cheap, already-computed signal to build that recovery
  logic on top of, without re-deriving "did this scene match anything"
  itself.
- **AI Vision-based ranking** (semantic similarity between a scene's
  narration/mood and an asset's actual visual content, using
  `MediaAsset.metadata` — reserved empty since Sprint 3.1 for exactly
  this). Explicitly out of scope per this sprint's brief; the current
  heuristics are a deliberate, inspectable placeholder for that richer
  signal, not an attempt to approximate it.
- **A configurable score floor** (discard candidates below some minimum
  score rather than always returning every candidate the provider found).
  No consumer needs this yet — Video Assembly taking the top-ranked
  candidate regardless of its absolute score is sufficient until a
  concrete case shows low-quality matches slipping through in practice.

## Sprint 6: Timeline Creation

### What changed

Introduced the **Timeline Creation** stage: turning Sprint 5's ranked
`AssetMatchPlan` into a `Timeline` — one selected, *downloaded* asset per
scene, in order, ready for a future rendering step to consume.

New domain objects: `TimelineClip` (value object — a `Scene` paired with
its selected `MediaAsset`) and `Timeline` (entity — an ordered list of
`TimelineClip`s, `asset_match_plan_id`, `total_duration_seconds`). New
exception: `TimelineCreationError`.

New application service: `TimelineService.create(asset_match_plan) ->
Timeline`. For each scene's `SceneAssetMatch`, it takes the best-ranked
candidate (`assets[0]` — no new scoring logic; Sprint 5 already ranked
best-first) and downloads it via a new `VideoSearchService.download()`
method.

`VideoSearchService.download(asset)` is additive: a thin public wrapper
around the private `_download_and_persist` this class already used inside
`discover()`. `discover()` and `search()` are completely unchanged.

New CLI: `scripts/create_timeline.py`, same two-mode shape (`topic` or
`--text`) as `scripts/match_assets.py`, extended one stage further.

### Why it fits the architecture

- **No new Port.** `TimelineService` depends on `VideoSearchService`
  directly — the exact same deliberate, documented exception
  `SceneAssetMatchingService` already established in Sprint 5. Selecting
  `assets[0]` is an in-process decision over data already inside the
  application, not a call to a new external system, so there is nothing
  here that needs a swappable boundary.
- **`VideoSearchService.download()` is exposure, not new behavior.** The
  download-and-persist code path already existed privately inside
  `discover()`; Sprint 6 just gives a caller that already has one specific
  `MediaAsset` in hand a way to invoke exactly that step, without
  re-searching or downloading every other candidate for that scene.
- **Timeline Creation is deliberately separated from Video Assembly.**
  Per the design review preceding this sprint: rendering (cutting
  narration + selected clips into an actual video file, via ffmpeg or
  similar) is a different responsibility and becomes Sprint 7, built on
  top of `Timeline` without changing its contract.
- **Fail-fast on unmatched scenes.** If any scene in the `AssetMatchPlan`
  has no candidate assets, `TimelineService.create()` raises
  `TimelineCreationError` naming every such scene, before downloading
  anything. A `Timeline` is the direct input to rendering — a gap here
  becomes a gap (e.g. a black frame) in the final video, which is worse
  than stopping now with a clear, actionable error.
- **`TimelineClip.metadata` / `Timeline.metadata` are extension points
  only**, added at the user's explicit request during the Sprint 6 design
  review, following the exact pattern `MediaAsset.metadata` (Sprint 3.1)
  already established in this codebase: empty `dict[str, Any]` by
  default, reserved for attributes a *future* rendering sprint will
  define (e.g. transitions, playback speed, zoom/pan, crop mode, fps,
  resolution, background music reference) — not guessed at or typed
  today, since the concrete shape isn't known yet and guessing wrong now
  would mean a breaking change later instead of a clean additive one.
  **No service in this sprint reads, writes, or validates either field.**
  Tests assert they default to `{}` and nothing more.

### Tests added

18 new tests, all against fakes, no network, no API keys:

- 6 in `test_video_search_service.py` for the new `download()` method:
  persists and sets `local_path`, does not call `search()`, propagates
  `AssetDownloadError`/provider errors/`StorageError` unchanged, and uses
  the same storage-key convention as `discover()`.
- 12 in `test_timeline_service.py` for `TimelineService`: one clip per
  scene in order, selects the best-ranked (`assets[0]`) candidate and
  downloads only that one, downloaded asset has `local_path` set,
  `Timeline` references the correct `asset_match_plan_id`, total duration
  is the last scene's `end_time`, `metadata` defaults to `{}` on both
  `Timeline` and `TimelineClip`, rejects an `AssetMatchPlan` with no
  matches, **fails fast** when any scene has no candidates (and names
  every such scene index), provider/storage errors propagate and stop
  processing at the failing scene, and `Timeline.to_dict()` includes
  clips and metadata correctly.

Total: **116 passing tests** (98 carried forward + 18 new).

### Example usage

```bash
python scripts/create_timeline.py "Titanic"
python scripts/create_timeline.py --text "The Titanic left Southampton in 1912." --duration 20
python scripts/create_timeline.py "Titanic" --json
```

```
============================================================
Timeline:          3f2a1c9e-...
Clips:             3
Total duration:    24.0s
============================================================
Scene 1  [0.0s - 8.0s]
Narration: The Titanic was the largest ship of its time...
Asset:     pexels:2499611  (/data/storage/video/pexels-2499611.mp4)
------------------------------------------------------------
Scene 2  [8.0s - 16.0s]
...
```

If any scene has no candidate assets, the command exits with status 1 and
a clear error naming exactly which scene indices need attention — no
partial `Timeline` is produced.

### Known limitations

- Same as every prior sprint that calls a real external API: no live
  end-to-end run against the real Anthropic/Pexels APIs was performed in
  the environment used to build this (no keys, no network egress to
  `api.anthropic.com` or `api.pexels.com` in this sandbox). The full test
  suite (116 tests, all against fakes) passes.
- Selection is always the single top-ranked candidate — there is no
  fallback if that specific download fails for a reason unrelated to the
  asset's rank (e.g. a transient provider timeout on an otherwise-good
  candidate); the whole `Timeline` creation stops, consistent with this
  sprint's fail-fast policy, rather than silently trying the next-ranked
  candidate.

### Future Enhancements (deliberately not built yet)

- **Video rendering/assembly** — actually cutting the narration audio and
  each clip's downloaded video into one final rendered file (ffmpeg,
  moviepy, or similar). This is Sprint 7, built directly on `Timeline`
  without changing its contract.
- **Falling back to the next-ranked candidate** if the top-ranked asset's
  download fails, instead of stopping the whole `Timeline`. Not built
  now because it's unclear whether that's the right recovery strategy
  without a real failure pattern to design against yet.
- **Scene-recovery for unmatched scenes** (broader query retry, generic
  b-roll fallback, manual-review flagging) — same deferred item Sprint 5
  already named; `TimelineCreationError` now names the exact scenes that
  would need this.
- **Giving `TimelineClip.metadata`/`Timeline.metadata` real, typed
  content** — transitions, playback speed, camera motion, fps,
  resolution, background music, render profile, etc. — once a rendering
  sprint defines what it actually needs. Deliberately left as an
  unvalidated `dict` today rather than guessed-at typed fields, per the
  Sprint 6 design review.

## Sprint 7: Video Rendering

### What changed

Introduced the **Video Rendering** stage: turning a `Timeline` plus its
narration audio into an actual, muxed MP4 file — the last stage of the
pipeline, `RenderedVideo`.

New domain objects: `RenderResult` (value object — a render engine's
un-persisted output: a temp file path plus `duration_seconds`/`width`/
`height`/`fps`) and `RenderedVideo` (entity — `timeline_id`, the persisted
`video_path`, `size_bytes`, and the same duration/resolution/fps fields).
New Port: `RenderPort`. New exception: `RenderError`.

New application service: `RenderService.render(timeline,
narration_audio_path) -> RenderedVideo`. New adapter:
`FfmpegRenderProvider` (`RenderPort`, shells out to local `ffmpeg`/
`ffprobe` binaries — normalizes each clip to one resolution/fps, trims it
to its scene's duration, concatenates all clips, then muxes the narration
audio on top). New CLI: `scripts/render_video.py`.

This sprint was preceded by an explicit design review of three points
raised before implementation began; all three changed the design from
its first-draft shape:

1. **`RenderPort.render()` takes `narration_audio_path: str`, not a
   `VoiceTrack`.** A render engine has no legitimate use for
   `VoiceTrack`'s other fields (`audio_id`, `script_id`, `provider`,
   `sample_rate`, `segments`) — coupling `RenderPort` to that entity would
   make rendering depend on voice-generation's domain shape for a value
   it never reads beyond `file_path`. The composition root
   (`scripts/render_video.py`) extracts `voice_track.file_path` itself;
   `RenderService`/`RenderPort` never see a `VoiceTrack`.
2. **`RenderResult` is a temp output path plus metadata, not
   `video_bytes`.** FFmpeg naturally produces a file, not an in-memory
   byte stream, and rendered video can be large enough that holding it as
   `bytes` on the result object would be wasteful. `RenderService` reads
   the temp file's bytes exactly once, persists them via the existing
   `StoragePort.save()` (same persistence boundary every other binary
   asset in this codebase already uses), and then deletes the temp file.
3. **`RenderedVideo` has no `provider_used` field**, a deliberate
   deviation from `Script`/`VoiceTrack`/`ScenePlan`, which do record
   their provider. Those entities' provider is a genuinely
   content-shaping choice (a different model produces materially
   different wording/voice/scene keywords); `RenderPort`'s contract is
   that any implementation produces the *same* video from the same
   inputs, so which engine rendered it is an interchangeable execution
   detail, not domain data — the same reasoning that already justified
   *not* adding `MediaAsset.metadata`-style speculative fields to
   `Timeline`/`TimelineClip` in Sprint 6. `RenderService` logs the render
   provider identity as structured logging instead, consistent with how
   every other service already logs its own provider identity without
   persisting it onto an entity.

### Why it fits the architecture

- **One new Port, and this is the correct call, not an ADR-006
  violation.** ADR-006 says a new Port is not introduced for in-process
  decisions over data already inside the application — it does not say
  "never introduce a new Port." Encoding a `Timeline` into a video file
  requires invoking a genuine external process (FFmpeg today, potentially
  a cloud renderer or Remotion/MoviePy later), the same category of real
  boundary that already justified `VideoSourcePort`/`VoiceGeneratorPort`/
  `ScriptGeneratorPort`/`ScenePlanningPort`. `RenderService` therefore
  depends on `RenderPort` (a Port), unlike `TimelineService`/
  `SceneAssetMatchingService`, which depend on a concrete sibling service
  because their core operations were in-process or already-existing
  external calls. Recorded as **ADR-007 — "Domain entities record
  provider identity only where the provider is a content-shaping choice,
  not for every entity a provider adapter touches."** This generalizes
  the reasoning behind point 3 of this sprint's design review (below) as
  a durable rule, the same way ADR-006 generalized Sprint 5/6's
  no-Port-for-in-process-decisions call.
- **`FfmpegRenderProvider`'s error mapping is subprocess-based, not
  HTTP-based**, unlike every other adapter in this codebase
  (`ClaudeScriptProvider`, `ElevenLabsVoiceProvider`, `PexelsProvider`).
  A non-zero exit code or a missing binary (`FileNotFoundError`) is
  wrapped in `RenderError` — there is no auth/timeout/quota distinction
  to make for a local subprocess the way there is for an HTTP provider,
  so `RenderError` stays a single type here rather than growing
  subclasses that don't correspond to any real distinguishable failure
  mode.
- **`RenderService` persists via the existing `StoragePort`, not a new
  capability.** Same reasoning Sprint 6 already applied to reusing
  `VideoSourcePort`/`StoragePort` for downloads: persisting arbitrary
  bytes under a key is not a new external boundary, so no new
  persistence Port was introduced for it.
- **Temp-file cleanup failure does not fail an otherwise-successful
  render.** By the time cleanup runs, the video is already safely
  persisted via `StoragePort` — a leftover temp file is a disk-hygiene
  concern, logged as a warning, not a reason to raise past a completed
  render.

### Tests added

15 new tests:

- 10 in `test_render_service.py`, entirely fake-based (`FakeRenderPort`
  writes a small real file so `RenderService`'s read-then-persist step has
  something genuine to read, without invoking FFmpeg): persists exactly
  once and returns a `RenderedVideo`, passes `narration_audio_path`
  (never a `VoiceTrack`) through to `RenderPort`, deletes the temp output
  file after persisting, rejects a `Timeline` with no clips, rejects an
  empty/whitespace `narration_audio_path`, `RenderError`/`StorageError`
  propagate unchanged and nothing is persisted on failure, raises if the
  reported output path is missing or the file is empty, and rendered
  video ids are unique across calls.
- 5 in `test_ffmpeg_render_provider.py`, against the **real** `ffmpeg`/
  `ffprobe` binaries (not mocked) using tiny synthetic fixtures generated
  via FFmpeg's own `lavfi` test sources — same "real, local, no network"
  testing precedent `test_local_fs_storage.py` already set for real
  filesystem I/O: renders a genuine two-clip timeline with narration
  audio and asserts the output file's actual probed
  width/height/duration; rejects an empty `Timeline`; rejects a missing
  narration audio file; rejects a missing `ffmpeg` binary; rejects a
  scene with non-positive duration before ever invoking `ffmpeg` on a
  degenerate trim. Automatically skipped in any environment without
  `ffmpeg`/`ffprobe` on `PATH`.

Total: **131 passing tests** (116 carried forward + 15 new).

### Example usage

```bash
python scripts/render_video.py "Titanic"
```

```
============================================================
Rendered video:    9c1e2b7a-...
File:              /data/storage/render/9c1e2b7a-....mp4
Duration:          24.0s
Resolution:        1080x1920 @ 30.0fps
Size:              4.83 MB
============================================================
```

There is no `--text` mode for this script, unlike
`scripts/create_timeline.py`: that mode builds a `VoiceTrack` with
`file_path=""` (no real audio was ever generated, only an estimated
duration), so there is nothing for `RenderService` to mux — rendering
always needs a real narration audio file on disk.

### Known limitations

- Same as every prior sprint that calls a real external API: no live
  end-to-end run against the real Anthropic/ElevenLabs/Pexels APIs was
  performed in the environment used to build this (no keys, no network
  egress to those hosts in this sandbox). `ffmpeg`/`ffprobe` themselves
  *are* installed and exercised for real in `test_ffmpeg_render_provider.py`
  (they're local binaries, not a network dependency). The full test suite
  (131 tests) passes.
- No transitions, effects, subtitles, or music — explicitly out of scope,
  same constraint the Sprint 6 proposal named for itself.
- Clips are trimmed and concatenated independently, with no cross-fade or
  frame-accurate sync guarantee beyond FFmpeg's own `-shortest` audio
  trim; a scene whose selected asset is shorter than its allotted
  duration will freeze on FFmpeg's default last-frame behavior for the
  concat demuxer rather than being flagged — not a new problem this
  sprint introduces, but not specifically handled either.
- `RenderResult`/`RenderedVideo`'s `fps` is whatever `ffprobe` measures on
  the actual output file, which may differ slightly from
  `settings.render_fps` due to encoder rounding — reported as measured,
  not as configured, deliberately (see `FfmpegRenderProvider._probe`'s
  docstring reasoning).

### Future Enhancements (deliberately not built yet)

- **Falling back to a different render engine** if FFmpeg fails for a
  reason unrelated to the input (e.g. a missing codec) — not built now
  because `RenderPort` only has one implementation today and there's no
  concrete second engine to fall back to yet.
- **Cross-fades / transitions between clips**, background music, and
  subtitles — explicitly out of scope per the founding constraint this
  project has carried since before Sprint 6.
- **Giving `RenderedVideo` a `provider_used` field**, if a genuine domain
  need for it appears (e.g. licensing terms that differ per render
  engine, or a UI that needs to disclose which renderer produced a given
  file) — see this sprint's design-review note above for why it was
  deliberately omitted for now rather than added speculatively.
- **A dedicated ADR file.** This project has referred to ADR-004/
  ADR-006/ADR-007 by number in-source and in this README since Sprint 5,
  but no standalone `docs/adr/*.md` file has ever actually been created —
  every "ADR" so far is a documented decision embedded in a module
  docstring and summarized here. Worth doing once there are enough of
  them that finding a specific one by scanning docstrings stops being
  practical.


## Sprint 8: Automatic Subtitle Generation

### What changed

Introduced the **Automatic Subtitle Generation** branch: splitting a
`ScenePlan`'s per-scene narration into readable, timed on-screen caption
cues, formatted as SRT and WebVTT and persisted alongside a
`RenderedVideo`. Unlike every prior sprint boundary, this one branches
directly off `ScenePlan` (Sprint 4's output) rather than extending the
`AssetMatchPlan -> Timeline -> RenderedVideo` chain — a `SubtitleTrack`'s
only data dependency is `ScenePlan`; it does not reference `Timeline` or
`RenderedVideo` at all (see below).

New domain entity: `SubtitleTrack` (`scene_plan_id`, `cues`,
`total_duration_seconds`, `created_at`) — deliberately format-agnostic,
exposing only `to_dict()`, no `to_srt()`/`to_vtt()`. New value object:
`SubtitleCue` (`index`, `scene_index`, `start_time`, `end_time`, `text`).
New exception: `SubtitleGenerationError`.

New application service: `SubtitleService.generate(scene_plan) ->
SubtitleTrack` (pure, no I/O) and `SubtitleService.export(track,
base_key) -> dict[str, StorageReference]` (async, persists via
`StoragePort`). New pure formatter (application layer, not domain):
`SubtitleFormatter.format_srt(track)` / `.format_vtt(track)`. New CLI:
`scripts/generate_subtitles.py`. `scripts/render_video.py` gained an
opt-in `--subtitle` flag that runs `SubtitleService` after rendering
completes, exporting `render/<id>.srt` / `render/<id>.vtt` alongside
`render/<id>.mp4` — `RenderService`/`RenderPort`/`Timeline`/
`RenderedVideo` are completely untouched by this addition.

**No new Port.** See "Why it fits the architecture" below.

### Why it fits the architecture

- **`SubtitleTrack` references only `scene_plan_id` — not `Timeline` or
  `RenderedVideo`.** Same "reference the one direct parent" ancestry
  convention `AssetMatchPlan`/`Timeline`/`RenderedVideo` already
  established. `SubtitleTrack`'s actual computational input is
  `ScenePlan`; it can be generated the moment Sprint 4 finishes,
  independent of whether asset matching, timeline creation, or rendering
  ever happen. Where a `SubtitleTrack`'s exported files are stored
  *alongside* a specific `RenderedVideo` is a composition-root storage-key
  naming convention (`render/<rendered_video_id>.srt`), not a
  domain-model concern — the entity itself never sees a `RenderedVideo`
  id.
- **No new Port — recorded as ADR-008.** `RenderPort` (Sprint 7) was
  justified because encoding a `Timeline` into a video file requires
  invoking a genuine external process. Nothing in this sprint has that
  shape: splitting narration into cues is a deterministic, in-process
  transformation over data the domain already owns (the same category of
  decision ADR-006 already kept Port-free for `TimelineService`/
  `SceneAssetMatchingService`), and caption-file serialization is equally
  in-process string formatting. Persistence of the resulting `.srt`/
  `.vtt` files reuses the existing `StoragePort` — a genuine external
  boundary, but not a *new* one.
- **SRT/VTT formatting lives in `SubtitleFormatter` (application layer),
  not on the `SubtitleTrack` entity.** A real deviation from the
  `to_dict()` convention every prior entity carries for JSON export —
  deliberate, not an oversight: SRT and WebVTT are external caption-file
  syntaxes with their own timecode punctuation and header conventions,
  concerns a domain entity has no business knowing about, the same way
  `Script` doesn't know it will eventually be serialized as an LLM API
  payload. `SubtitleFormatter.format_srt()`/`.format_vtt()` are stateless
  `@staticmethod`s — deterministic, no I/O, no injected dependencies.
- **Hybrid proportional timing, not word-count alone.** Each cue's
  on-screen duration is allocated from its Scene's `[start_time,
  end_time]` window proportionally to `weight = 0.7 * character_count +
  0.3 * word_count`, not word count alone — a cue built from a few long
  words needs more reading time than word count alone would allocate it.
  Still fully deterministic (no AI, no speech alignment, no external
  provider), applying one additional weighting term to the same
  proportional-timing *category* of technique `ScenePlanningService`
  already uses and documents for deriving Scene timing itself.
- **Cues never cross a Scene boundary.** Every cue produced for one Scene
  has its `start_time`/`end_time` entirely within that Scene's own
  window. A very short Scene may therefore produce a single cue shorter
  than `min_cue_seconds` — accepted deliberately rather than crossing
  into a neighboring Scene's time window, which would make a
  `SubtitleCue.scene_index` ambiguous and would reintroduce the "two
  sources of truth for timing" problem `TimelineClip`'s own docstring
  already rejected once.
- **`SubtitleCue` carries `scene_index: int`, not the full `Scene`
  object** — a deliberate deviation from the `TimelineClip`/
  `SceneAssetMatch` precedent of embedding the whole `Scene`. Those two
  value objects have a strict 1:1 cardinality with their Scene;
  `SubtitleCue` does not (one Scene commonly produces several cues), so
  embedding the full `Scene` on every resulting cue would duplicate its
  narration/keywords/mood across N cues for one scene, for no downstream
  reader.

### Tests added

43 new tests:

- 6 in `test_subtitle_track.py`: `SubtitleTrack.create()` assigns
  id/created_at, `total_duration_seconds` is the last cue's `end_time`
  (or `0.0` for an empty track), `to_dict()` includes every cue field, and
  a regression guard proving `SubtitleTrack` exposes no `to_srt()`/
  `to_vtt()`; `SubtitleCue` is immutable.
- 10 in `test_subtitle_formatter.py`: SRT blocks are sequentially
  numbered, SRT/VTT timecodes use the correct comma/period millisecond
  separator and roll over minutes/hours correctly, empty-track output for
  both formats, WebVTT always starts with the `WEBVTT` header (even when
  empty) and has no numeric cue identifiers, multiline cue text is
  preserved in both formats, and the formatter is stateless.
- 20 in `test_subtitle_service.py`: a short scene produces exactly one
  cue spanning its full window; a long scene produces multiple
  non-overlapping cues in order; cue text respects
  `max_chars_per_line`/`max_lines_per_cue`; a single overlong word still
  gets its own line rather than being dropped or split; cue indices are
  renumbered `1..len(cues)` across the whole track, not reset per scene;
  cues never cross a scene boundary; `min_cue_seconds` is enforced when
  the scene's own duration allows it, and falls back to an even split
  when it doesn't; rejects a `ScenePlan` with no scenes and fails fast
  naming every scene with empty/whitespace-only narration; constructor
  rejects non-positive configuration; `export()` persists both `.srt`/
  `.vtt` under the given base key with the correct content types, and
  propagates `StorageError` from either write, stopping before the `.vtt`
  write if the `.srt` write fails.
- 5 in `test_generate_subtitles_cli.py` and 5 in
  `test_render_video_cli.py`: argparse-level CLI behavior for both
  scripts (`topic` required, `--subtitle`/`--rendered-video-id`/tuning
  flags default correctly and are captured when passed), extracted into a
  standalone `build_arg_parser()` in each script specifically so this is
  testable without invoking any provider or network call.
- 2 sanity assertions exercised via the above but worth naming
  explicitly: SRT/VTT round-trip timing correctness (a cue's timecodes in
  the formatted output match its own `start_time`/`end_time` to the
  millisecond) and scene-boundary correctness are both covered as part of
  `test_subtitle_service.py` and `test_subtitle_formatter.py` above
  rather than as separate files.

Total: **174 passing tests** (131 carried forward + 43 new).

### Example usage

```bash
python scripts/generate_subtitles.py "Titanic"
```

```
============================================================
Subtitle track:    9c1e2b7a-...
Cues:              6
Duration:          24.0s
SRT file:          /data/storage/subtitles/9c1e2b7a-....srt
VTT file:          /data/storage/subtitles/9c1e2b7a-....vtt
============================================================
[1] 0.00s – 4.10s (scene 0)
The Titanic left Southampton in 1912.
------------------------------------------------------------
...
```

Generating subtitles alongside a specific rendered video, saved under the
same storage-key prefix as that video's own `.mp4`:

```bash
python scripts/render_video.py "Titanic" --subtitle
```

```
============================================================
Rendered video:    9c1e2b7a-...
File:              /data/storage/render/9c1e2b7a-....mp4
Duration:          24.0s
Resolution:        1080x1920 @ 30.0fps
Subtitles (SRT):   /data/storage/render/9c1e2b7a-....srt
Subtitles (VTT):   /data/storage/render/9c1e2b7a-....vtt
Size:              4.83 MB
============================================================
```

### Known limitations

- **Cue timing is only as accurate as `Scene.start_time`/`end_time`**,
  which are themselves a proportional-word-count approximation (see
  `ScenePlanningService`'s own documented reasoning), not measured
  timing. This sprint inherits that imprecision rather than introducing
  it — the same way `AssetMatchPlan`/`Timeline`/`RenderedVideo` already
  do. If a future timing-capable voice provider populates
  `VoiceTrack.segments`, subtitle accuracy would improve automatically
  without a code change here, since Scene timing is already downstream of
  that data.
- **Cue-splitting is chunk/word-count-based, not clause/punctuation-aware.**
  Splitting can occasionally produce a cue break mid-thought. A
  deliberate, inspectable placeholder, the same posture Sprint 5 took
  toward its own ranking heuristic — not an attempt to fully solve
  subtitle typesetting quality in one sprint.
- **Fails fast on empty narration**, the same posture
  `TimelineCreationError` already documents for itself — correct for
  MVP, a candidate for "flag and continue" if this pipeline ever runs
  unattended at scale.
- Same as every prior sprint that calls a real external API: no live
  end-to-end run against the real Anthropic/ElevenLabs APIs was performed
  in the environment used to build this. The full test suite (174 tests)
  passes without any network access.

### Future Enhancements (deliberately not built yet)

- **Hard-burned (open) captions**, via an additive extension to
  `RenderPort`, once there is a concrete need for captions that cannot be
  toggled off by the viewer. Not built now because it is a rendering-stage
  concern (touches `Timeline`/`RenderPort`, not `ScenePlan`) and mixing it
  into this sprint would repeat the same one-responsibility violation
  Sprint 6/7 already refused to make between "select an asset" and
  "encode a video."
- **`SubtitleStyle`** — font, size, alignment, colors, outline, shadow,
  reveal animation, karaoke-style per-word highlighting, and
  platform-specific presets. Explicitly named as a future extension point
  in `SubtitleFormatter`'s own module docstring; nothing in this sprint's
  code references or guesses at its eventual shape.
- **Translated `SubtitleTrack`s**, once a translation provider boundary
  exists — a natural, cheap first increment of a future multi-language
  pipeline.
- **Word-level (karaoke) cue timing**, once a provider adapter actually
  populates `VoiceTrack.segments` — no adapter in this codebase does
  today (confirmed in `ElevenLabsVoiceProvider`'s own docstring).
- **A dedicated ADR file.** Still named, still not done — same item
  Sprint 7's own README already flagged for itself. This sprint adds
  ADR-008 to the same in-docstring/in-README convention rather than
  introducing a new documentation format on its own.
