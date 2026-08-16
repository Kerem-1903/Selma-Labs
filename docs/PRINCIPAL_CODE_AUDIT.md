# Principal Code Audit — Local Music-First Factory

## Scope and Verdict

This is a source-level audit of the music-first execution path: durable
orchestration, JSON persistence, FFmpeg rendering/frame extraction, WhisperX,
Librosa, Pexels, and karaoke ASS output. It does not claim that every external
provider or the full test suite was executed in this environment.

| Severity | Finding | Evidence |
| --- | --- | --- |
| **P0** | FFmpeg/FFprobe have no timeout or cancellation cleanup. | `infrastructure/providers/render/ffmpeg_render_provider.py:458` |
| **P0** | Two terminals can lose updates and duplicate a run stage. | `infrastructure/repositories/local_json_run_repository.py:28`, `core/application/orchestration/run_executor.py:44` |
| **P1** | ASS word tags can outlive their dialogue event. | `core/application/services/premium_subtitle_formatter.py:50` |
| **P1** | `PipelineRun.artifact_manifest` is externally mutable. | `core/domain/entities/pipeline_run.py:38` |
| **P1** | WhisperX cancellation does not stop inference; cached GPU models have no lifecycle. | `infrastructure/providers/audio/whisperx_word_alignment_provider.py:72` |
| **P1** | Frame extraction repeats the unmanaged subprocess pattern. | `infrastructure/providers/frame_extraction/ffmpeg_frame_extractor.py:33` |
| **P2** | Pexels malformed payloads/empty direct downloads are not normalized at the port. | `infrastructure/providers/video/pexels_provider.py:108`, `:139` |
| **P2** | Legacy vision scoring logs then accepts heuristic candidates on failure. | `core/application/services/vision_asset_scoring_service.py:147` |

The domain boundaries are generally strong. The real enterprise risks are
operational: cancellation, inter-process ownership, and subtitle timing
quantization.

## P0 — FFmpeg/FFprobe resource leaks

### Evidence

`FfmpegRenderProvider._run` awaits `process.communicate()` indefinitely at
`infrastructure/providers/render/ffmpeg_render_provider.py:458-475`. It has
no timeout, no `CancelledError` branch, and no `finally` that terminates a
still-running child. Cancelling the asyncio task can therefore leave FFmpeg
or FFprobe alive. `shutil.rmtree(..., ignore_errors=True)` at lines `102-103`
and `174-175` only removes files; it cannot stop a process. The same defect
exists in `FfmpegFrameExtractor` lines `33-43` and local-audio FFprobe.

The legacy `render()` path creates a final temporary output at renderer line
`94`. If mux/probe fails, that empty output is not unlinked.

### Mandatory replacement

Add `import os` and `import subprocess`, plus positive
`subprocess_timeout_seconds` and `termination_grace_seconds` constructor
arguments. Replace `_run` and add `_stop_process` with this code:

```python
async def _run(
    self,
    command: list[str],
    *,
    context: str,
    capture: bool = False,
) -> str:
    process: asyncio.subprocess.Process | None = None
    creation_kwargs: dict[str, object] = {}
    if os.name == "nt":
        creation_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        creation_kwargs["start_new_session"] = True

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            **creation_kwargs,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=self._subprocess_timeout_seconds,
        )
    except FileNotFoundError as error:
        raise RenderExecutionError(
            f"Could not find binary '{command[0]}' while {context}."
        ) from error
    except TimeoutError as error:
        if process is not None:
            await asyncio.shield(self._stop_process(process))
        raise RenderExecutionError(
            f"Timed out after {self._subprocess_timeout_seconds:.0f}s while {context}."
        ) from error
    except asyncio.CancelledError:
        if process is not None:
            await asyncio.shield(self._stop_process(process))
        raise
    finally:
        if process is not None and process.returncode is None:
            await asyncio.shield(self._stop_process(process))

    if process.returncode != 0:
        stderr_text = (stderr_bytes or b"").decode("utf-8", errors="replace")[-2_000:]
        raise RenderExecutionError(
            f"FFmpeg failed while {context} (exit code {process.returncode}): {stderr_text}"
        )
    return (stdout_bytes or b"").decode("utf-8", errors="replace")

async def _stop_process(self, process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(
            process.communicate(),
            timeout=self._termination_grace_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.communicate()
```

Apply this helper to the renderer, frame extractor, and local-audio FFprobe.
In legacy `render()`, track `final_path` and unlink it in `finally` unless the
render/probe path completed. For hard interpreter death or power loss, Python
`finally` is insufficient: run workers under a Windows Job Object with
`KILL_ON_JOB_CLOSE`, or systemd/Kubernetes process containment on Linux.

## P0 — JSON is atomic, not concurrency-safe

### Evidence

`os.replace` at `local_json_run_repository.py:57-67` protects against a
partially-written target file. It does not protect the read-modify-write
transaction. Two terminals can both read an incomplete run at
`RunExecutor.execute_stage:44`, run the same paid operation, and overwrite
one another. They also share the same temporary name `<run_id>.json.tmp` at
repository line `62`.

### Mandatory replacement

Use a per-run inter-process lock that spans **get → operation → save**. Add
`filelock>=3.16` to `requirements.txt`, extend `RunRepositoryPort` with
`lock_run()`, and use a unique temporary filename:

```python
# core/domain/ports/run_repository_port.py
from contextlib import AbstractAsyncContextManager

class RunRepositoryPort(ABC):
    @abstractmethod
    def lock_run(self, run_id: str) -> AbstractAsyncContextManager[None]:
        """Exclusively lease one run for the complete stage transition."""
        raise NotImplementedError
```

```python
# infrastructure/repositories/local_json_run_repository.py
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from filelock import FileLock, Timeout

@asynccontextmanager
async def lock_run(self, run_id: str) -> AsyncIterator[None]:
    self._validate_run_id(run_id)
    self._base_directory.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(self._base_directory / f"{run_id}.lock"))
    try:
        await asyncio.to_thread(lock.acquire, timeout=self._lock_timeout_seconds)
    except Timeout as error:
        raise PipelineRunStateError(
            f"Timed out waiting for pipeline run '{run_id}' ownership."
        ) from error
    try:
        yield
    finally:
        await asyncio.to_thread(lock.release)

def _write_run(self, data: dict[str, Any]) -> None:
    run_id = str(data["run_id"])
    self._validate_run_id(run_id)
    self._base_directory.mkdir(parents=True, exist_ok=True)
    target_path = self._path_for(run_id)
    temporary_path = self._base_directory / f".{run_id}.{uuid.uuid4().hex}.tmp"
    try:
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary_path, target_path)
    finally:
        temporary_path.unlink(missing_ok=True)
```

```python
# core/application/orchestration/run_executor.py
async def execute_stage(self, run_id: str, stage_name: str, operation: StageOperation) -> StageArtifact:
    async with self._repository.lock_run(run_id):
        run = await self._repository.get_by_id(run_id)
        if run.has_completed_stage(stage_name):
            return run.get_stage_artifact(stage_name)
        if run.status is PipelineRunStatus.COMPLETED:
            raise PipelineRunStateError(
                f"Completed run has no artifact for requested stage '{stage_name}'."
            )
        run.begin_stage(stage_name)
        await self._repository.save(run)
        try:
            artifact = operation()
            if inspect.isawaitable(artifact):
                artifact = await artifact
            if not isinstance(artifact, dict):
                raise TypeError("A pipeline stage operation must return a dictionary.")
            run.mark_stage_completed(stage_name, artifact)
            await self._repository.save(run)
            return run.get_stage_artifact(stage_name)
        except asyncio.CancelledError:
            run.mark_failed(f"Stage '{stage_name}' was cancelled.")
            await asyncio.shield(self._repository.save(run))
            raise
        except Exception as error:
            run.mark_failed(f"Stage '{stage_name}' failed: {error}")
            await self._repository.save(run)
            raise
```

For multiple workers, replace file locking with an expiring database lease and
optimistic revision compare-and-swap. Do not use local JSON on a network share.

## P1 — `PipelineRun` aggregate encapsulation leak

### Evidence

`artifact_manifest` is a public mutable dataclass field at
`core/domain/entities/pipeline_run.py:38`. `get_stage_artifact()` and
`to_dict()` deep-copy their returns, but callers can mutate
`run.artifact_manifest` directly or retain the dict supplied to the
constructor. A reproduced direct mutation makes a stage appear complete with
no state transition and no repository save.

### Mandatory replacement

Store the manifest privately and expose only an immutable snapshot. Replace
the public field and its related methods with this contract; update
`__post_init__`, `to_dict`, and `from_dict` to use `_artifact_manifest`.

```python
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

@dataclass(init=False)
class PipelineRun:
    run_id: str
    status: PipelineRunStatus
    current_stage: str
    retry_count: int
    failure_reason: str | None
    max_retries: int
    created_at: datetime
    updated_at: datetime
    _artifact_manifest: dict[str, dict[str, Any]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __init__(
        self,
        run_id: str,
        status: PipelineRunStatus = PipelineRunStatus.PENDING,
        current_stage: str = "PENDING",
        retry_count: int = 0,
        artifact_manifest: Mapping[str, Mapping[str, Any]] | None = None,
        failure_reason: str | None = None,
        max_retries: int = 3,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.run_id = run_id
        self.status = PipelineRunStatus(status)
        self.current_stage = current_stage
        self.retry_count = retry_count
        self.failure_reason = failure_reason
        self.max_retries = max_retries
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self._artifact_manifest = deepcopy(dict(artifact_manifest or {}))
        self.__post_init__()

    @property
    def artifact_manifest(self) -> Mapping[str, Mapping[str, Any]]:
        """Return an immutable snapshot; never expose aggregate internals."""
        return MappingProxyType(deepcopy(self._artifact_manifest))

    def has_completed_stage(self, stage_name: str) -> bool:
        return stage_name in self._artifact_manifest

    def get_stage_artifact(self, stage_name: str) -> dict[str, Any]:
        return deepcopy(self._artifact_manifest[stage_name])

    def mark_stage_completed(
        self,
        stage_name: str,
        artifact_data: dict[str, Any],
    ) -> None:
        self._require_stage_name(stage_name)
        if self.status is not PipelineRunStatus.RUNNING:
            raise PipelineRunStateError("Only a running pipeline run can complete a stage.")
        if self.current_stage != stage_name:
            raise PipelineRunStateError(
                f"Cannot complete '{stage_name}' while '{self.current_stage}' is active."
            )
        if not isinstance(artifact_data, dict):
            raise ValueError("Pipeline stage artifact_data must be a dictionary.")
        self._artifact_manifest[stage_name] = deepcopy(artifact_data)
        self._touch()
```

Add a test that mutates both the constructor argument and the property return
value; neither may change aggregate state.

## P1 — Karaoke ASS centisecond drift

### Evidence

`PremiumSubtitleFormatter._centiseconds` rounds each interval independently
at `core/application/services/premium_subtitle_formatter.py:67-69`, while
`_format_timecode` rounds event boundaries separately at lines `72-77`.
Python `round()` also uses banker’s rounding. Reproduction: three 15ms words
emit `\k2 + \k2 + \k2` (60ms), while their 45ms dialogue event ends at four
centiseconds. Karaoke can therefore continue after the dialogue event ends.

### Mandatory replacement

Quantize the complete cue once and distribute its integer centiseconds across
ordered gaps and words. Replace `_format_cue`, `_karaoke_text`,
`_centiseconds`, and `_format_timecode` with:

```python
def _format_cue(self, cue: SubtitleCue) -> str:
    if not cue.words:
        raise KaraokeFormattingError(
            "Premium ASS formatting requires word-timed SubtitleCue values."
        )
    start_cs = self._milliseconds_to_centiseconds(cue.start_ms)
    end_cs = self._milliseconds_to_centiseconds(cue.end_ms)
    karaoke_text = self._karaoke_text(cue, total_centiseconds=end_cs - start_cs)
    return (
        "Dialogue: 0,"
        f"{self._format_timecode(start_cs)},"
        f"{self._format_timecode(end_cs)},"
        f"Karaoke,,0,0,0,,{karaoke_text}"
    )

def _karaoke_text(self, cue: SubtitleCue, *, total_centiseconds: int) -> str:
    intervals: list[tuple[int, str, bool]] = []
    cursor_ms = cue.start_ms
    for word in cue.words:
        if word.start_ms < cursor_ms:
            raise KaraokeFormattingError("Karaoke words must not overlap.")
        gap_ms = word.start_ms - cursor_ms
        if gap_ms:
            intervals.append((gap_ms, r"\h", False))
        intervals.append((word.end_ms - word.start_ms, self._escape(word.text), True))
        cursor_ms = word.end_ms

    units = self._allocate_centiseconds(intervals, total_centiseconds)
    return " ".join(
        rf"{{\k{centiseconds}}}{text}"
        for centiseconds, (_, text, _) in zip(units, intervals)
        if centiseconds > 0
    )

@staticmethod
def _milliseconds_to_centiseconds(milliseconds: int) -> int:
    if milliseconds < 0:
        raise KaraokeFormattingError("ASS timestamps must not be negative.")
    return (milliseconds + 5) // 10

@staticmethod
def _allocate_centiseconds(
    intervals: list[tuple[int, str, bool]],
    total_centiseconds: int,
) -> list[int]:
    if total_centiseconds <= 0:
        raise KaraokeFormattingError("Cue duration must be positive.")
    units = [milliseconds // 10 for milliseconds, _, _ in intervals]
    minimums = [1 if is_word else 0 for _, _, is_word in intervals]
    units = [max(unit, minimum) for unit, minimum in zip(units, minimums)]
    if sum(units) > total_centiseconds:
        raise KaraokeFormattingError(
            "Cue cannot be represented at ASS centisecond precision."
        )

    ranked = sorted(
        range(len(intervals)),
        key=lambda index: (intervals[index][0] % 10, intervals[index][2]),
        reverse=True,
    )
    remaining = total_centiseconds - sum(units)
    while remaining:
        for index in ranked:
            if remaining == 0:
                break
            units[index] += 1
            remaining -= 1
    return units

@staticmethod
def _format_timecode(total_centiseconds: int) -> str:
    hours, remainder = divmod(total_centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
```

Property-test invariant: emitted `\k` units must sum exactly to dialogue end
minus start for every valid cue.

## P1 — WhisperX lifecycle and cancellation are incomplete

### Evidence

`WhisperXWordAlignmentProvider` caches its transcription model and one model
per language at
`infrastructure/providers/audio/whisperx_word_alignment_provider.py:72-79`
and `:89-113`. This is good for latency, but long-lived workers have no
shutdown hook, no eviction, no `gc.collect()`, and no CUDA cache release.

At line `72`, `asyncio.to_thread` protects the event loop but does **not**
make model inference cancellable. Cancelling the awaiting coroutine leaves the
worker thread and potentially VRAM-heavy inference running until completion.
Python cannot safely kill a running thread.

### Mandatory replacement

Add deterministic shutdown for normal process teardown and call it from the
composition root’s `finally`/service-lifecycle hook:

```python
# infrastructure/providers/audio/whisperx_word_alignment_provider.py
import gc

async def aclose(self) -> None:
    """Release cached model references after all factory work has finished."""
    await asyncio.to_thread(self._release_models)

def _release_models(self) -> None:
    with self._inference_lock:
        self._alignment_models.clear()
        self._transcription_model = None
        gc.collect()
        if not self._device.lower().startswith("cuda"):
            return
        try:
            import torch
        except ImportError:
            return
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
```

For real cancellation/timeout guarantees, move `_align_sync` into a dedicated
worker process with request/result queues. Terminate and restart that child on
timeout; do not try to terminate the `to_thread` worker. Also change lines
`140-148` to reject malformed response containers. Only timestamp-less words
are a documented condition that may be filtered; malformed segments/words
must become `WordAlignmentError` and produce an observability counter.

## P2 — Provider error normalization and exception swallowing

### Pexels response boundary

`PexelsProvider.search` calls `response.json()` at
`infrastructure/providers/video/pexels_provider.py:108` without a typed
wrapper. A 200 HTML error page or malformed `videos` list leaks library
exceptions outside the port. `download` returns empty bytes at line `139`;
`VideoSearchService` catches it later, but direct port callers do not receive
the documented `AssetDownloadError`.

```python
try:
    payload = response.json()
except (TypeError, ValueError) as error:
    raise ProviderError("Pexels returned invalid JSON.") from error
if not isinstance(payload, dict) or not isinstance(payload.get("videos", []), list):
    raise ProviderError("Pexels returned an invalid video-search payload.")

try:
    assets = [self._map_video(item, query) for item in payload.get("videos", [])]
except (KeyError, TypeError, ValueError) as error:
    raise ProviderError("Pexels returned an invalid video item.") from error

# download(), after HTTP status validation
if not response.content:
    raise AssetDownloadError(f"Pexels returned empty content for asset '{asset.id}'.")
return response.content
```

### Vision fallback

`VisionAssetScoringService.score_scene` logs the exception at lines `160-165`
but returns the original heuristic candidate. This is not an unlogged error,
but it is a semantic fallback that bypasses vision evidence in legacy flows.
The music-first `score_visual_intent` path correctly rejects at lines
`197-204`. If `score_scene` remains reachable from any premium automation,
add a `require_vision_evidence` policy and raise
`VisualAssetNotFoundError` instead of returning the heuristic candidate.

### Librosa result

No swallowed Librosa error was found. Its broad adapter catch at
`infrastructure/providers/audio/librosa_highlight_selector.py:83-88` preserves
the causal exception and maps it to `HighlightSelectionError`, which is
correct. Its remaining operational caveat is the same `to_thread`
cancellation limitation as WhisperX.

## Required regression matrix

1. A deliberately hanging FFmpeg command must timeout, exit, and leave no
   child PID after cancellation.
2. Two Python processes targeting one `run_id` must execute the operation
   once; the second process must return the persisted artifact.
3. A crash between temporary JSON write and replace must preserve the prior
   canonical run file.
4. Randomized ordered cues must always satisfy: sum of `\k` units equals
   dialogue duration exactly.
5. Repeated CUDA WhisperX construct/close cycles must return allocated and
   reserved VRAM to the expected baseline.
6. Pexels HTML, invalid JSON, malformed items, and empty bodies must surface
   only typed provider/domain errors.
7. Rendering/frame extraction cancellation must reclaim temporary directories
   and subprocesses.

## Remediation order

1. Centralize managed subprocess execution and reuse it for FFmpeg/FFprobe.
2. Add run ownership locking, unique JSON temporary names, and inter-process
   tests.
3. Privatize `PipelineRun` artifacts.
4. Replace independent ASS rounding with cue-level allocation.
5. Add WhisperX shutdown now; schedule process isolation before concurrent or
   long-lived GPU deployment.
6. Normalize Pexels malformed/empty responses and remove legacy vision
   fallback from every premium path.
