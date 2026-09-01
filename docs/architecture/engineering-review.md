# SELMA Labs — Engineering Review v1.2

**Status:** Living reference, updated incrementally per project decision.
v1.0 covered the Sprint 5 snapshot only; v1.1 added Sprint 6 and Sprint 7;
this revision (v1.2) adds Sprint 8, independently re-verified against the
actually-implemented Sprint 8 code in this session (running `pytest`
directly, reading the source) — not carried forward from the Sprint 8
proposal document without re-checking. Update procedure going forward, per
project decision: after each milestone, update `docs/project/status.md`,
`README.md`, and this document together — this file is not meant to be
regenerated from scratch each time, but revised incrementally as the
codebase changes.

**Covers:** Sprint 8 codebase as the current implementation snapshot at
the time of writing. §1-§13 below describe the Sprint 5 snapshot exactly
as v1.0 left them (still accurate for the layers/ports/adapters that
haven't changed); §15 covers Sprint 6/7 exactly as v1.1 left it;
**§16 (new)** covers everything Sprint 8 added or changed. Read §1-§13 for
the foundation, §15 for Sprint 6/7, §16 for what's current.

**Source of truth for this revision:** the Sprint 8 code implemented in
this session — its source, its tests (`pytest` run directly: 174 passing),
and its own `README.md` section. Sprint 3/4/5/6/7 code was not
re-examined for this revision since §1-§15 already independently verified
it and nothing in Sprint 8 touched it.

---

## 1. Overall Architecture

Ports & Adapters (Hexagonal), verified directly from imports across all 60
Python source files (tests excluded from that count). Three layers:

```
core/domain            <- entities, value objects, Port ABCs, exceptions
core/application        -> depends only on core/domain
infrastructure           -> implements core/domain Ports
config                    -> composition: settings.py + provider_registry.py
scripts/*.py               -> five CLI composition roots, one per sprint
```

No web server, no database, no queue exists in this codebase — every
capability is invoked through a CLI script.

## 2. Layers and Dependency Direction

Confirmed by reading every import statement, not inferred:

- `core/domain/**` imports nothing from `core/application` or
  `infrastructure`. Zero exceptions found.
- `core/application/services/*.py` import only from `core/domain/*`
  (entities, value objects, `core/domain/ports/*`, `core/domain/exceptions.py`)
  — never a concrete provider class, with one named exception (§5).
- `infrastructure/providers/*` and `infrastructure/storage/*` are the only
  files importing third-party SDKs (`anthropic`, `httpx`, `mutagen`) or
  doing raw filesystem I/O.
- `config/provider_registry.py` is the only file importing both
  `config.settings` and concrete provider classes together.
- `scripts/*.py` are the only files importing both `config.*` and
  `core.application.services.*` together.

Dependency direction is one-way and consistent everywhere it was checked.

## 3. Domain Model

**Entities** (identity-bearing, `id`/`audio_id` field):

| Entity | Sprint (per in-ZIP README headings) | Key fields |
|---|---|---|
| `Script` | 1 | `id`, `topic`, `full_text`, `target_duration_seconds`, `provider_used`, `estimated_word_count` |
| `VoiceTrack` | 2 | `audio_id`, `script_id`, `duration_seconds`, `provider`, `voice_name`, `sample_rate`, `file_path`, `segments` |
| `ScenePlan` | 4 | `id`, `script_id`, `voice_track_id`, `total_duration_seconds`, `provider_used`, `scenes: list[Scene]` |
| `MediaAsset` | 3, extended in 3.1 | `id`, `provider`, `provider_asset_id`, `media_type`, `original_url`, `thumbnail_url`, `width`, `height`, `duration_seconds`, `fps`, `tags`, `attribution`, `license`, `local_path`, `metadata` |
| `AssetMatchPlan` | 5 | `id`, `scene_plan_id`, `matches: list[SceneAssetMatch]` |

Correction against my own prior review's phrasing: **"Sprint 3.1" is
explicitly named inside the in-ZIP `README.md`** (a full section heading,
`## Sprint 3.1: MediaAsset Identity + Metadata Extension`, plus five
further references to it elsewhere in the same document). It's part of
the uploaded project, not something that only existed in conversation —
I'm correcting that here rather than repeating the earlier
mischaracterization. Per that section, Sprint 3.1 added
`provider_asset_id` (required identity field) and `metadata` (an open,
empty-by-default `dict`, reserved for future AI Vision-derived
attributes) to `MediaAsset`.

**Value objects** (no identity):

| VO | Sprint | Fields |
|---|---|---|
| `GeneratedAudio` | 2 | `audio_bytes`, `duration_seconds`, `sample_rate`, `provider`, `voice_name`, `segments` |
| `StorageReference` | 2 | `key`, `path`, `size_bytes` |
| `SpeechSegment` | 2.1 | `text`, `start`, `end` — always empty in this codebase; no wired provider populates it |
| `Scene` | 4 | `index`, `narration`, `search_keywords`, `detected_objects`, `location`, `mood`, `visual_priority`, `start_time`, `end_time` |
| `SceneAssetMatch` | 5 | `scene`, `assets: list[MediaAsset]` (best-ranked first), `has_matches` (derived) |

**Relationships**, confirmed by reading the `.create()`/constructor calls
directly: `VoiceTrack.script_id → Script.id`. `ScenePlan.script_id →
Script.id` and `ScenePlan.voice_track_id → VoiceTrack.audio_id` (both
parents referenced directly — the only entity in the codebase with two
immediate parents). `AssetMatchPlan.scene_plan_id → ScenePlan.id`.
`SceneAssetMatch` carries a full `Scene` object, not just its index.

## 4. Ports

Five Port ABCs exist under `core/domain/ports/`, all with `async` abstract
methods:

1. **`ScriptGeneratorPort`** — `generate_script(topic, target_duration_seconds) -> Script`.
2. **`VoiceGeneratorPort`** — `generate_voice(text, voice_name) -> GeneratedAudio`.
3. **`StoragePort`** — `save(key, data, content_type) -> StorageReference`.
4. **`VideoSourcePort`** — `search(query, max_results) -> list[MediaAsset]`, `download(asset) -> bytes`.
5. **`ScenePlanningPort`** — property `provider_identity -> str`, `plan_scenes(narration_text) -> list[Scene]`.

Each Port's docstring states the class(es) that implement it and the
typed exceptions it can raise — confirmed to match the actual
implementations' `raise` statements in every adapter I read.

## 5. Services

Five application services under `core/application/services/`:

- **`ScriptService`** — validates topic (non-empty) and duration
  (15–90s), calls `ScriptGeneratorPort`, validates output word count
  against a 150-WPM-derived expected range (0.5×–1.6×).
- **`VoiceService`** — validates script has narration text, calls
  `VoiceGeneratorPort`, validates non-empty audio and positive duration,
  persists via `StoragePort`, builds `VoiceTrack`.
- **`VideoSearchService`** — two public methods: `discover()` (searches,
  raises on zero results, downloads+persists every result) and `search()`
  (searches, does not raise on zero results, does not download — used by
  asset matching). Both share a private validation/search helper.
- **`ScenePlanningService`** — validates narration text and
  `voice_track.duration_seconds > 0`, calls `ScenePlanningPort` for scene
  *content* only, computes scene *timing* itself by allocating the
  measured `VoiceTrack.duration_seconds` proportionally by word count
  (its own docstring states the reasoning: an LLM has no reliable sense
  of elapsed seconds, so timing is computed from the one genuinely
  measured number in the pipeline instead of asked of the provider).
- **`SceneAssetMatchingService`** — for each `Scene` in a `ScenePlan`,
  calls `VideoSearchService.search()` and ranks candidates with a
  deterministic scoring heuristic (keyword overlap, orientation, duration
  coverage — read directly from the module).

All five services take their dependencies via constructor injection
against Port interfaces — **except `SceneAssetMatchingService`, which
depends on `VideoSearchService` directly**, a concrete class, not a Port.
This is stated and justified in that module's own docstring (ranking
already-fetched candidates is an in-process transform, not a call to a
new external system) — reported here as the one deviation from "services
depend only on Ports" found anywhere in this codebase.

## 6. Infrastructure Adapters

| Adapter | Port | External dependency | Error mapping (from source) |
|---|---|---|---|
| `ClaudeScriptProvider` | `ScriptGeneratorPort` | Anthropic Messages API (`anthropic` SDK) | timeout/connection → `ProviderTimeoutError`; 401 → `ProviderAuthError`; 429 → `ProviderQuotaExceededError`; other → `ProviderError` |
| `ElevenLabsVoiceProvider` | `VoiceGeneratorPort` | ElevenLabs REST API via raw `httpx` (not their SDK) | timeout → `ProviderTimeoutError`; connect/other → `ProviderConnectionError`; 401 → `ProviderAuthError`; 429 → `ProviderQuotaExceededError`; 400/404/422 → `InvalidVoiceConfigurationError`; other → `ProviderError`; MP3-metadata parse failure → `ProviderError` |
| `CachingVoiceProvider` | `VoiceGeneratorPort` (decorator) | Local filesystem only | inner-provider errors propagate unchanged; corrupt cache entries treated as a miss, not an error |
| `LocalFsStorage` | `StoragePort` | Local filesystem only | `OSError` → `StorageError` |
| `PexelsProvider` | `VideoSourcePort` | Pexels Video API via raw `httpx` | same pattern as ElevenLabs; download non-200 → `AssetDownloadError` |
| `ClaudeScenePlanningProvider` | `ScenePlanningPort` | Anthropic Messages API | same Anthropic-status mapping as `ClaudeScriptProvider`, plus `ScenePlanningError` for invalid/non-list JSON or a scene missing required `narration` |

Self-declared limitations found directly in adapter docstrings:
`ElevenLabsVoiceProvider` always leaves `GeneratedAudio.segments` empty
(no timestamped-endpoint integration yet); `PexelsProvider` falls back to
the search query as a tag when Pexels returns none; `LocalFsStorage`
accepts but ignores `content_type` (kept only for interface compatibility
with a hypothetical future backend).

## 7. Configuration System

`config/settings.py` — a `pydantic-settings` `BaseSettings` subclass,
env-file driven (`.env`), lazily constructed via a cached `get_settings()`
function (not instantiated at import time — its own comment states this
is deliberate, so importing the module doesn't require a `.env` file to
exist). Fields cover: Anthropic key + script model, voice provider
selection (`Literal["elevenlabs"]`) + related keys/ids, storage root dir,
voice-cache toggle + dir, video provider selection (`Literal["pexels"]`) +
key + default max results, scene planning provider selection
(`Literal["claude"]`) + model.

`config/provider_registry.py` — three factory functions:
`get_voice_provider()`, `get_video_source_provider()`,
`get_scene_planning_provider()`. Each reads the corresponding `Literal`
setting and returns the matching concrete Port implementation, raising
`ValueError` for an unrecognized value. Currently only capabilities with
more than one plausible provider are registered here. `LocalFsStorage`
and `ClaudeScriptProvider` are instantiated directly by the CLI
composition roots instead — read from the code as an observed design
choice (each has exactly one implementation today, and no `Literal`
switch exists for either in `config/settings.py`), not as an
architectural violation. Whether it should be extended if/when a second
storage backend or script provider is ever added is a design question,
not a defect.

**No `.env.example` file exists anywhere in the uploaded ZIP** — see §12
(Documentation Improvements) for how this is classified.

## 8. CLI Entry Points

Five scripts under `scripts/`, one per sprint, each a composition root
(the only place that imports both concrete provider classes and
`config.*` together):

| Script | Wires |
|---|---|
| `generate_script_test.py` | `ClaudeScriptProvider` → `ScriptService` |
| `generate_voice.py` | `get_voice_provider()` + `LocalFsStorage` → `VoiceService` (optional chained `ScriptService`) |
| `search_assets.py` | `get_video_source_provider()` + `LocalFsStorage` → `VideoSearchService` |
| `plan_scenes.py` | Claude script/voice providers → `ScenePlanningService` (optional chained Script/Voice) |
| `match_assets.py` | `get_video_source_provider()` + `LocalFsStorage` → `VideoSearchService` → `SceneAssetMatchingService` (optional full chain) |

Each supports a `--text`/narration-only mode alongside a full-topic mode,
consistently across scripts 2, 4, and 5.

## 9. Existing Tests

9 test files under `tests/unit/`, **98 tests total**, confirmed by running
the suite directly against this exact snapshot: `98 passed`. Every
application service has a dedicated test file (`test_script_service.py`,
`test_voice_service.py`, `test_scene_planning_service.py`,
`test_scene_asset_matching_service.py`, and `VideoSearchService` covered
inside `test_video_search_service.py`). Provider-level adapters with real
error-mapping logic have their own test files too
(`test_pexels_provider.py`, `test_claude_scene_planning_provider.py`,
`test_caching_voice_provider.py`, `test_local_fs_storage.py`).
`ClaudeScriptProvider` and `ElevenLabsVoiceProvider` have no adapter-level
test file of their own — they're exercised only indirectly through
`ScriptService`'s/`VoiceService`'s tests, worth stating plainly rather
than assuming full direct coverage.

Every test file defines its own local `Fake*Port` class(es) — no shared
fakes module exists. No test in this suite requires network access or an
API key, confirmed by reading every test file rather than assuming the
pattern held throughout.

**Test count tracking** (per review feedback — kept as a running record
in this document from now on):

| Sprint | Tests | Verified how |
|---|---|---|
| 5 | 98 | Ran `pytest` directly against the uploaded Sprint 5 ZIP |

Future rows will be added here once each subsequent sprint's code is
actually uploaded and its suite actually run — not pre-filled in advance.
I'm intentionally not adding a "Sprint 6 → 116" row now: that number
comes from Sprint 6 work that exists only as a conversation artifact, not
inside any uploaded ZIP, and this document's whole value is that every
number in it was independently verified against uploaded code. Once
Sprint 6's code is uploaded (or re-uploaded) as part of the project, its
real count gets added here the same way Sprint 5's was.

## 10. Completed Roadmap

Per the code and the in-ZIP `README.md`'s own section headings:

| Sprint | Delivered |
|---|---|
| 1 | Script Generation — `ScriptGeneratorPort`, `ClaudeScriptProvider`, `ScriptService` |
| 2 | Voice Generation — `VoiceGeneratorPort`, `StoragePort`, `ElevenLabsVoiceProvider`, `LocalFsStorage`, `VoiceService` |
| 2.1 | `CachingVoiceProvider`, `SpeechSegment` |
| 3 | Video Search — `VideoSourcePort`, `PexelsProvider`, `MediaAsset`, `VideoSearchService` |
| 3.1 | `MediaAsset` extended with `provider_asset_id` and `metadata` |
| 4 | Scene Planning — `ScenePlanningPort`, `ClaudeScenePlanningProvider`, `ScenePlan`, `ScenePlanningService`, timing estimation |
| 5 | Scene Asset Matching — `AssetMatchPlan`, `SceneAssetMatch`, `VideoSearchService.search()`, `SceneAssetMatchingService`, deterministic ranking, `match_assets.py` |

Five Ports, five services, six provider/adapter classes, 98 passing
tests — all confirmed directly.

## 11. Remaining Roadmap

Nothing beyond §10 exists in code. The in-ZIP `README.md` is the only
in-project source that speaks to what comes next, and its own words (from
Sprint 5's "Future Enhancements" section) name, without committing to a
sprint number or detailed design:

- Selecting and downloading exactly one asset per scene (the README's own
  text explicitly ties this to "Video Assembly (Sprint 6+)").
- Recovering from an unmatched scene (broader query, generic b-roll
  fallback, manual-review flag) — built on the already-existing
  `SceneAssetMatch.has_matches` signal.
- AI Vision-based ranking using `MediaAsset.metadata` (reserved empty
  since Sprint 3.1 for exactly this).
- A configurable score floor for discarding low-quality candidates.

I'm reporting these because they are literally present in the uploaded
README text, not because I'm asserting they constitute an approved
Sprint 6 plan — no such plan exists inside the uploaded project.

## 12. Technical Debt

**Intentional** (explicitly named as a tradeoff in-source):
- `VideoSourcePort` bundles `search()` and `download()` on one interface
  rather than splitting download into its own capability.
- No `CachePort` abstraction — caching stays a `VoiceGeneratorPort`
  decorator only.
- `SceneAssetMatchingService` depends on `VideoSearchService` directly
  instead of a new Port (§5).

**Not explicitly acknowledged anywhere in the uploaded project:**
- `provider_registry.py` covers capabilities with more than one plausible
  provider only; storage and script generation are wired directly in
  every script instead (§7). Reframed per review feedback: this is a
  design choice observed in the code, not unacknowledged debt — listed
  here only because no comment in the code states the reasoning
  explicitly, not because the choice itself looks wrong.

**Potential future problems** (not bugs today):
- `CachingVoiceProvider`'s on-disk cache has no eviction policy.
- `ScenePlan`'s proportional-word-count timing model is a known
  approximation (its own docstring says so); every downstream consumer of
  `Scene.start_time`/`end_time` inherits that imprecision until a
  timing-capable voice provider is wired in.

**Documentation Improvements** (not code-quality issues — moved out of
Technical Debt per review feedback, since they affect onboarding/DX, not
correctness):
- No `.env.example` file exists anywhere in the uploaded ZIP. Every
  adapter's own constructor error message names the one variable it
  needs, but nothing lists the full expected set together in one place.

## 13. Architectural Concerns

No hard dependency-direction violations found anywhere in the uploaded
project. One item worth naming, already covered above and
self-documented in the code rather than hidden:

1. `SceneAssetMatchingService` → `VideoSearchService` direct dependency
   (§5) — a deviation from "every service depends only on a Port,"
   explicitly justified in-source.

The `provider_registry.py` coverage pattern (§7) is reclassified per
review feedback from "architectural concern" to "observed design choice"
— it does not violate dependency direction and is listed under §12 only
as an area with no explicit in-code comment explaining the choice, not
as a concern in itself.

## 14. Anything That Should Be Discussed Before Sprint 6

- **What exactly Sprint 6 is scoped to do.** Nothing inside the uploaded
  project defines it — the README's Future Enhancements text (§11) names
  several candidate directions (asset selection/download, unmatched-scene
  recovery, AI Vision ranking, score floor) without picking one or
  sequencing them.
- **Whether the `provider_registry.py` asymmetry (§7/§12/§13) should be
  addressed**, left alone, or simply noted as known and irrelevant to
  whatever Sprint 6 turns out to be.
- **Whether the missing `.env.example` (§7/§12) is worth fixing** as a
  small, low-risk documentation addition, independent of Sprint 6's
  actual scope.

I have not proposed solutions to any of the above — flagging only, per
your rules. Waiting for your direction before any Sprint 6 discussion or
code.

## 15. Sprint 6 and Sprint 7 (added in v1.1)

Everything below was independently re-verified against
`selma-labs-sprint6.zip`'s source and the Sprint 7 code added in this
session, the same standard §1-§14 already applied to Sprint 5 — not
copied from either sprint's own proposal document without re-checking.

### 15.1 New Entities / Value Objects

| Type | Sprint | Kind | Key fields |
|---|---|---|---|
| `Timeline` | 6 | Entity | `id`, `asset_match_plan_id`, `clips: list[TimelineClip]`, `total_duration_seconds`, `metadata: dict` |
| `TimelineClip` | 6 | Value object | `scene: Scene` (full object, not just index), `asset: MediaAsset`, `metadata: dict` |
| `RenderResult` | 7 | Value object | `output_path`, `duration_seconds`, `width`, `height`, `fps` |
| `RenderedVideo` | 7 | Entity | `id`, `timeline_id`, `video_path`, `size_bytes`, `duration_seconds`, `width`, `height`, `fps`, `created_at` |

Confirmed by direct source read: `Timeline.total_duration_seconds` and
`metadata` are **stored fields**, not derived/absent as an earlier draft
of the Sprint 6 proposal document argued for — the actually-implemented
code took the opposite position from that draft on both points. Reporting
this here rather than silently reconciling it, per this document's own
standard of only stating what the code actually does.

`RenderedVideo` deliberately has **no `provider_used` field**, unlike
`Script`/`VoiceTrack`/`ScenePlan` (§3). This was an explicit design-review
decision in Sprint 7 (see README's Sprint 7 section for the full
reasoning) — confirmed absent by reading `core/domain/entities/rendered_video.py`
directly, not assumed from the discussion that produced it.

### 15.2 New Ports

6\. **`RenderPort`** — `render(timeline, narration_audio_path: str) ->
RenderResult`. Confirmed by source read: takes a plain `str` path, not a
`VoiceTrack` — an explicit Sprint 7 design-review decision, verified
against the actual method signature rather than assumed from discussion.

### 15.3 New Services

- **`TimelineService`** (Sprint 6) — `create(asset_match_plan) ->
  Timeline`. Depends on `VideoSearchService` directly (concrete class, not
  a Port) — same documented deviation `SceneAssetMatchingService` already
  established in Sprint 5 (§5), now the second instance of this pattern.
- **`RenderService`** (Sprint 7) — `render(timeline,
  narration_audio_path) -> RenderedVideo`. Depends on `RenderPort` and
  `StoragePort` — both genuine Ports, unlike `TimelineService`. Verified
  by source read: never imports or references `VoiceTrack`.

### 15.4 New Adapters

| Adapter | Port | External dependency | Error mapping (from source) |
|---|---|---|---|
| `FfmpegRenderProvider` | `RenderPort` | Local `ffmpeg`/`ffprobe` binaries (subprocess, not network) | non-zero exit code or missing binary → `RenderError` (single type; no auth/timeout/quota distinction exists for a local subprocess, unlike every HTTP-backed adapter in §6) |

### 15.5 Dependency Direction Check (Sprint 6/7 code)

Re-run for the new code, same method as §2 (reading every import
statement directly): no `core/domain/**` file imports from
`core/application`/`infrastructure`; `render_service.py` and
`timeline_service.py` import only from `core.domain.*`;
`ffmpeg_render_provider.py` is the only new file importing a third-party
process (`asyncio.create_subprocess_exec`) or doing subprocess I/O.
`config/provider_registry.py` gained one new factory
(`get_render_provider`) following the existing pattern exactly. Zero
violations found.

### 15.6 New ADRs

- **ADR-006** (Sprint 6, confirmed still applies) — no new Port for
  in-process decisions over data already inside the application.
- **ADR-007** (Sprint 7) — domain entities record provider identity only
  where the provider is a content-shaping choice, not for every entity a
  provider adapter touches. Generalizes the reasoning behind
  `RenderedVideo` omitting `provider_used`. Neither ADR exists as a
  standalone `docs/adr/*.md` file — both are documented decisions embedded
  in module docstrings and summarized in the README, consistent with how
  every "ADR" in this project has been recorded since Sprint 5. Flagging
  this as a documentation gap worth closing once there are enough ADRs
  that scanning docstrings to find one stops being practical — not a
  defect in either decision itself.

### 15.7 Test Count Tracking (continuing §9's table)

| Sprint | Tests | Verified how |
|---|---|---|
| 5 | 98 | Ran `pytest` directly against the uploaded Sprint 5 ZIP |
| 6 | 116 | Ran `pytest` directly against `selma-labs-sprint6.zip` (98 carried forward + 18 new, all against fakes) |
| 7 | 131 | Ran `pytest` directly against the Sprint 7 code added this session (116 carried forward + 15 new: 10 fake-based in `test_render_service.py`, 5 against real `ffmpeg`/`ffprobe` in `test_ffmpeg_render_provider.py`) |

### 15.8 Technical Debt / Concerns Update

No new hard dependency-direction violations (§15.5). Two additional
deliberate, self-documented deviations from "every service depends only
on a Port," joining the one §5/§13 already named:

- `TimelineService` → `VideoSearchService` direct dependency (Sprint 6,
  same justification as §5).

`RenderService` does **not** join this list — it depends on `RenderPort`,
a genuine Port, which is itself worth noting as evidence the pattern is a
considered case-by-case call (§5's original reasoning: "a Port exists to
abstract an external boundary — there is no boundary here to abstract")
rather than a rule being eroded sprint over sprint.

### 15.9 Remaining Roadmap (superseding §11 and §14)

The pipeline is now end-to-end complete: `Script -> VoiceTrack -> ScenePlan
-> AssetMatchPlan -> Timeline -> RenderedVideo`. Per `docs/project/status.md`
(updated alongside this document), nothing is currently scoped as the next
sprint. Named-but-unsequenced candidates carried forward from earlier
sprints' own "Future Enhancements" sections: unmatched-scene recovery
(Sprint 5), falling back to the next-ranked candidate on download failure
(Sprint 6), AI Vision-based ranking using `MediaAsset.metadata` (Sprint
3.1), render-engine fallback and transitions/subtitles/music (Sprint 7).
None of these have been designed or committed to a sprint number — naming
them here only because they're the actual named candidates in-project, not
asserting a plan.

## 16. Sprint 8 (added in v1.2)

Everything below was independently re-verified against the Sprint 8 code
implemented in this session, the same standard §1-§15 already applied —
not copied from the Sprint 8 proposal document without re-checking.

### 16.1 New Entities / Value Objects

| Type | Sprint | Kind | Key fields |
|---|---|---|---|
| `SubtitleTrack` | 8 | Entity | `id`, `scene_plan_id`, `cues: list[SubtitleCue]`, `total_duration_seconds`, `created_at` |
| `SubtitleCue` | 8 | Value object | `index`, `scene_index` (int, not the full `Scene`), `start_time`, `end_time`, `text` |

Confirmed by direct source read: `SubtitleTrack` exposes only `to_dict()`
— no `to_srt()`/`to_vtt()` — a deliberate deviation from the `to_dict()`
convention every prior entity carries, verified by reading
`core/domain/entities/subtitle_track.py` directly rather than assumed from
the proposal document's discussion of it. `test_subtitle_track.py`
contains a standing regression test (`test_subtitle_track_has_no_format_methods`)
asserting this stays true.

`SubtitleCue` carries `scene_index: int`, not the full `Scene` object —
confirmed by reading `core/domain/value_objects/subtitle_cue.py` directly;
a real, documented deviation from the `TimelineClip`/`SceneAssetMatch`
precedent of embedding the whole `Scene` (§3), justified by a cardinality
difference (one `Scene` commonly produces several `SubtitleCue`s, unlike
the strict 1:1 those two value objects have), not an oversight.

### 16.2 New Ports

**None.** Confirmed by reading every new file's imports directly: no new
file under `core/domain/ports/` was added, and `SubtitleService` (§16.3)
imports only `StoragePort` from `core.domain.ports`. Recorded as
**ADR-008 — "No new Port for subtitle generation or serialization;
`StoragePort` is reused for persistence."** This directly extends
ADR-006's reasoning (§15.6) to a second category of in-process decision
(text formatting) it did not originally have an example of.

### 16.3 New Services

- **`SubtitleService`** (Sprint 8) — `generate(scene_plan) ->
  SubtitleTrack` (confirmed by source read: plain `def`, not `async def` —
  no `await` anywhere in the method body, unlike every other
  service-entrypoint method in this codebase) and `async def
  export(track, base_key) -> dict[str, StorageReference]`. Depends on
  `StoragePort` only — no dependency on `VideoSearchService`, `RenderPort`,
  or any other application-layer class, confirmed by reading its
  constructor signature directly.
- **`SubtitleFormatter`** (Sprint 8) — `format_srt(track)` /
  `format_vtt(track)`, both `@staticmethod`. Confirmed by source read:
  the class has no `__init__` beyond the implicit default and is never
  instantiated anywhere in the codebase (`grep -rn "SubtitleFormatter("`
  only matches the two static-method calls, never a constructor call).

### 16.4 New Adapters

**None.** Confirmed by directory listing: no new file was added under
`infrastructure/`. `LocalFsStorage` (Sprint 2) is reused unmodified for
persisting `.srt`/`.vtt` content — verified by reading
`core/application/services/subtitle_service.py`'s `export()` method, which
calls `self._storage.save()` with UTF-8-encoded text and a `content_type`
of `"text/plain"`/`"text/vtt"`, exactly the same call shape every other
`StoragePort.save()` call site in this codebase already makes.

### 16.5 Dependency Direction Check (Sprint 8 code)

Re-run for the new code, same method as §2/§15.5 (reading every import
statement directly): no `core/domain/**` file imports from
`core/application`/`infrastructure`; `subtitle_service.py` imports only
`core.domain.*` plus `subtitle_formatter.py` (a sibling application-layer
module, not a domain import); `subtitle_formatter.py` imports only
`core.domain.entities.subtitle_track`/`core.domain.value_objects.subtitle_cue`
and has zero imports of anything infrastructure-related. `scripts/render_video.py`
and `scripts/generate_subtitles.py` both had their argparse setup
extracted into a standalone `build_arg_parser()` function specifically so
CLI behavior is unit-testable without a live provider call — a
composition-root-level refactor, not a change to any domain or application
contract. Zero violations found.

### 16.6 New ADRs

- **ADR-008** (Sprint 8) — no new Port for subtitle generation
  (cue-splitting) or serialization (SRT/WebVTT formatting); `StoragePort`
  is reused for persistence. Directly extends ADR-006's reasoning (§15.6)
  to a second category of in-process decision. Not a standalone
  `docs/adr/*.md` file, same as ADR-006/ADR-007 — a documented decision
  embedded in `subtitle_service.py`'s module docstring and summarized in
  the README, consistent with how every "ADR" in this project has been
  recorded since Sprint 5. The documentation-gap flag from §15.6 (worth a
  standalone file once there are enough of these) still applies and is
  not resolved by this sprint.

### 16.7 Test Count Tracking (continuing §9's/§15.7's table)

| Sprint | Tests | Verified how |
|---|---|---|
| 7 | 131 | Ran `pytest` directly against the Sprint 7 code (§15.7) |
| 8 | 174 | Ran `pytest` directly against the Sprint 8 code added this session (131 carried forward + 43 new: 6 in `test_subtitle_track.py`, 10 in `test_subtitle_formatter.py`, 20 in `test_subtitle_service.py`, 5 in `test_generate_subtitles_cli.py`, 5 in `test_render_video_cli.py` — the last two argparse-only, no network) |

### 16.8 Technical Debt / Concerns Update

No new dependency-direction violations (§16.5). No new instance of the
"service depends on a concrete sibling service instead of a Port" pattern
(§5/§15.8) — `SubtitleService` depends only on `StoragePort`, a genuine
Port, the same category `RenderService` already fell into (§15.8's
closing note), not `TimelineService`/`SceneAssetMatchingService`'s
direct-dependency pattern. The zero-new-Port, zero-new-adapter shape of
this sprint (§16.2/§16.4) is unusual relative to every prior sprint except
Sprint 3.1 — flagged here as worth double-checking on its own terms
(and argued for at length in the Sprint 8 proposal's own §5/§13/§15),
not asserted without scrutiny just because it is convenient.

### 16.9 Remaining Roadmap (superseding §15.9)

The pipeline is now end-to-end complete through rendering, with
`SubtitleTrack` as a parallel branch off `ScenePlan` independent of
`AssetMatchPlan -> Timeline -> RenderedVideo`. Per `docs/project/status.md`
(updated alongside this document), nothing is currently scoped as the next
sprint. Named-but-unsequenced candidates carried forward: unmatched-scene
recovery (Sprint 5), download-failure fallback (Sprint 6), AI
Vision-based ranking (Sprint 3.1), render-engine fallback (Sprint 7), and
— newly named this sprint — hard-burned captions, `SubtitleStyle`,
translated subtitles, and word-level (karaoke) cue timing (all Sprint 8's
own "Future Enhancements," see README). None of these have been designed
or committed to a sprint number.

---



This is v1.2, updated incrementally per project decision, covering
Sprint 8 in addition to v1.1's Sprint 6/7 coverage and v1.0's Sprint 5
baseline. Going forward:

- Update this document **incrementally**, alongside `docs/project/status.md`
  and `README.md`, at the end of each sprint — not regenerated from
  scratch.
- Every fact added must be independently re-verified against the
  then-current uploaded ZIP (running the test suite, reading the actual
  source) — the same standard applied throughout this version — not
  carried forward from a prior conversation's memory.
- A new Claude session can be given this document plus the current ZIP
  and should be able to reconstruct an accurate understanding of the
  project and continue from where development left off.
