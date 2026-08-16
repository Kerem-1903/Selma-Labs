"""
SubtitleService — application-layer orchestration for turning a ScenePlan
into a persisted, dual-format (SRT + WebVTT) SubtitleTrack.

Bridges Sprint 4's output (ScenePlan, where every Scene already carries
finalized narration text and start_time/end_time) to a new "Automatic
Subtitle Generation" pipeline branch. Unlike every other sprint boundary
in this codebase, this one branches directly off ScenePlan rather than
extending the AssetMatchPlan -> Timeline -> RenderedVideo chain -- a
SubtitleTrack's only data dependency is ScenePlan (see SubtitleTrack's own
docstring for why it deliberately does not reference Timeline or
RenderedVideo). It is *sequenced* after Sprint 7 (rendering) for product
and delivery reasons -- a caption file's value is realized together with a
finished, watchable video -- not because of any technical dependency.

Two responsibilities, split the way SubtitleFormatter/StoragePort were
asked to be used:

  1. ``generate()`` -- pure, synchronous, no I/O. Splits every Scene's
     narration into one or more readable SubtitleCues and assembles a
     SubtitleTrack. SubtitleService orchestrates this; it does not format
     or persist anything here.
  2. ``export()`` -- async. Uses SubtitleFormatter (pure formatting, no
     I/O of its own) to produce SRT/VTT strings, then persists both via
     an injected StoragePort -- the same persistence boundary every other
     text/binary asset in this codebase already goes through (voice
     audio, downloaded video clips, rendered video).

This split -- "SubtitleService orchestrates, SubtitleFormatter formats,
StoragePort stores" -- mirrors RenderService's own three-way split
("RenderService orchestrates, RenderPort encodes, StoragePort stores"),
substituting a pure formatter for what RenderService needed a genuine
external Port for (see the "New Ports" section below for why no such Port
exists here).

--------------------------------------------------------------------------
Depends on StoragePort only -- no new Port (ADR-008)
--------------------------------------------------------------------------
RenderPort (Sprint 7) was justified because encoding a Timeline into a
video file requires invoking a genuine external process (FFmpeg).
Nothing in this sprint has that shape:

  - Cue generation (splitting Scene.narration into readable cues with
    timing) is a deterministic, in-process transformation over data the
    domain layer already fully owns -- no external system is consulted.
    This is the same category of decision TimelineService's "pick
    assets[0]" and SceneAssetMatchingService's "join search_keywords into
    a query string" already were, and both were kept Port-free under
    ADR-006 rather than hidden behind a speculative Port. The same
    reasoning applies here.
  - Caption-file serialization (SRT/VTT syntax) is likewise purely
    in-process -- see SubtitleFormatter's own module docstring.
  - Persistence of the resulting .srt/.vtt files *is* a genuine external
    boundary, but not a *new* one -- StoragePort already exists for
    exactly this purpose (Sprint 2) and is agnostic to what content it is
    given. Introducing a second, subtitle-specific storage Port would
    duplicate a boundary this codebase already crossed, for no new
    capability.

--------------------------------------------------------------------------
Timing algorithm: hybrid proportional (character-count-weighted)
--------------------------------------------------------------------------
Cue duration is NOT allocated by word count alone. A pure word-count split
under-serves cues built from a few long words and over-serves cues built
from many short ones -- readers need time to read *characters*, not just
to hear word boundaries pass. Each cue's weight is instead:

    weight = 0.7 * character_count + 0.3 * word_count

and a Scene's [start_time, end_time] window is divided across its cues
proportionally to weight. This is deliberately still deterministic --
no AI, no speech alignment, no external provider -- and is the same
proportional-timing *category* of technique ScenePlanningService already
uses and documents as an accepted approximation for deriving Scene timing
itself from VoiceTrack duration; this sprint applies one additional,
slightly richer weighting term to that established methodology rather
than inventing an unrelated one.

Cues never cross a Scene boundary: every cue produced for one Scene has
its start_time/end_time entirely within that Scene's own start_time/
end_time. A very short Scene may therefore produce a single cue shorter
than ``min_cue_seconds`` -- deliberately accepted rather than crossing
into a neighboring Scene's time window, which would make a SubtitleCue's
``scene_index`` ambiguous and would reintroduce the "two sources of truth
for timing" problem TimelineClip's own docstring already rejected once
(see SubtitleCue's docstring).

Deliberately NOT implemented in this sprint (see also
SubtitleFormatter's module docstring for the SubtitleStyle extension
point):
  - Word-level/karaoke timing -- VoiceTrack.segments (SpeechSegment) is
    the field that would carry this, but no provider adapter in this
    codebase populates it today.
  - Clause/punctuation-aware splitting -- splitting is done on
    chunk/word-count boundaries within a Scene's narration, not on
    sentence or clause boundaries. A deliberate, inspectable placeholder,
    the same posture Sprint 5 took toward its own ranking heuristic.
  - Translation, hard-burned (open) captions, and subtitle styling --
    each named as a Future Enhancement, not built here.
"""
from __future__ import annotations

import logging

from core.application.services.subtitle_formatter import SubtitleFormatter
from core.domain.entities.scene_plan import ScenePlan
from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.exceptions import SubtitleGenerationError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.storage_reference import StorageReference
from core.domain.value_objects.subtitle_cue import SubtitleCue

logger = logging.getLogger("selma.subtitle_service")

SUBTITLE_CONTENT_TYPES = {
    "srt": "text/plain",
    "vtt": "text/vtt",
    "ass": "text/x-ssa",
}

# Hybrid proportional timing weights (see module docstring).
_CHARACTER_WEIGHT = 0.7
_WORD_WEIGHT = 0.3


class SubtitleService:
    """Splits a ScenePlan's per-scene narration into a timed SubtitleTrack
    (``generate()``), and formats + persists that track as SRT/VTT via an
    injected StoragePort (``export()``)."""

    def __init__(
        self,
        storage: StoragePort,
        max_chars_per_line: int = 42,
        max_lines_per_cue: int = 2,
        min_cue_seconds: float = 1.2,
    ) -> None:
        if max_chars_per_line <= 0:
            raise ValueError("max_chars_per_line must be positive.")
        if max_lines_per_cue <= 0:
            raise ValueError("max_lines_per_cue must be positive.")
        if min_cue_seconds <= 0:
            raise ValueError("min_cue_seconds must be positive.")
        self._storage = storage
        self._max_chars_per_line = max_chars_per_line
        self._max_lines_per_cue = max_lines_per_cue
        self._min_cue_seconds = min_cue_seconds

    def generate(self, scene_plan: ScenePlan) -> SubtitleTrack:
        """Produce a SubtitleTrack from ``scene_plan``. Pure -- no I/O.

        Args:
            scene_plan: The ScenePlan whose scenes' narration/timing will
                be split into readable, timed cues, in scene order.

        Returns:
            A SubtitleTrack with one or more SubtitleCues per scene, cue
            ``index`` values renumbered 1..len(cues) across the whole
            track (not reset per scene).

        Raises:
            SubtitleGenerationError: ``scene_plan`` has no scenes, or one
                or more scenes have empty/whitespace-only narration --
                names every such scene index.
        """
        if not scene_plan.scenes:
            raise SubtitleGenerationError(
                "ScenePlan has no scenes to generate subtitles from."
            )

        empty_narration_indices = [
            scene.index for scene in scene_plan.scenes if not scene.narration.strip()
        ]
        if empty_narration_indices:
            raise SubtitleGenerationError(
                "Cannot generate subtitles: the following scenes have "
                f"empty narration: {empty_narration_indices}."
            )

        logger.info(
            "subtitle_generation_started",
            extra={"scene_plan_id": scene_plan.id, "scene_count": len(scene_plan.scenes)},
        )

        cues: list[SubtitleCue] = []
        next_index = 1
        for scene in scene_plan.scenes:
            for text, (start, end) in self._cues_for_scene(scene):
                cues.append(
                    SubtitleCue(
                        index=next_index,
                        scene_index=scene.index,
                        start_time=start,
                        end_time=end,
                        text=text,
                    )
                )
                next_index += 1

        track = SubtitleTrack.create(scene_plan_id=scene_plan.id, cues=cues)

        logger.info(
            "subtitle_generation_completed",
            extra={
                "scene_plan_id": scene_plan.id,
                "subtitle_track_id": track.id,
                "cue_count": len(track.cues),
                "total_duration_seconds": track.total_duration_seconds,
            },
        )

        return track

    async def export(
        self, track: SubtitleTrack, base_key: str
    ) -> dict[str, StorageReference]:
        """Format ``track`` as SRT and WebVTT and persist both via
        StoragePort under ``'{base_key}.srt'`` / ``'{base_key}.vtt'``.

        Args:
            track: The SubtitleTrack to export.
            base_key: Storage-key prefix (no extension) both files are
                saved under -- typically correlated with a RenderedVideo's
                id by the composition root so the two files sit alongside
                the rendered video they caption (see
                scripts/generate_subtitles.py / scripts/render_video.py's
                ``--subtitle`` flag). SubtitleTrack itself never sees or
                stores this value -- see SubtitleTrack's own docstring.

        Returns:
            A dict with keys ``"srt"``/``"vtt"``, each mapping to the
            StorageReference for that file.

        Raises:
            StorageError: either write failed. The ``.srt`` write is
                attempted first; if it fails, the ``.vtt`` write is never
                attempted -- same fail-fast-and-stop behavior every other
                multi-step service in this codebase already follows.
        """
        srt_text = SubtitleFormatter.format_srt(track)
        vtt_text = SubtitleFormatter.format_vtt(track)
        ass_text = SubtitleFormatter.format_ass(track)

        srt_reference = await self._storage.save(
            key=f"{base_key}.srt",
            data=srt_text.encode("utf-8"),
            content_type=SUBTITLE_CONTENT_TYPES["srt"],
        )
        vtt_reference = await self._storage.save(
            key=f"{base_key}.vtt",
            data=vtt_text.encode("utf-8"),
            content_type=SUBTITLE_CONTENT_TYPES["vtt"],
        )
        ass_reference = await self._storage.save(
            key=f"{base_key}.ass",
            data=ass_text.encode("utf-8"),
            content_type=SUBTITLE_CONTENT_TYPES["ass"],
        )

        logger.info(
            "subtitle_export_completed",
            extra={
                "subtitle_track_id": track.id,
                "srt_key": srt_reference.key,
                "vtt_key": vtt_reference.key,
            },
        )

        return {"srt": srt_reference, "vtt": vtt_reference, "ass": ass_reference}

    # -- Internal helpers ------------------------------------------------

    def _cues_for_scene(
        self, scene: Scene
    ) -> list[tuple[str, tuple[float, float]]]:
        """Return ``[(cue_text, (start_time, end_time)), ...]`` for one
        Scene, entirely within that scene's own start_time/end_time."""
        chunks = self._wrap_narration(scene.narration)
        windows = self._allocate_windows(chunks, scene.start_time, scene.end_time)
        return list(zip(chunks, windows))

    def _wrap_narration(self, narration: str) -> list[str]:
        """Split ``narration`` into cue texts: greedily fill lines up to
        ``max_chars_per_line``, then group consecutive lines into cues of
        at most ``max_lines_per_cue`` lines, joined with ``"\\n"``.

        A single word longer than ``max_chars_per_line`` is still placed
        on its own line rather than dropped or split mid-word -- the line
        limit is a soft target for wrapping, not a hard truncation rule.
        """
        words = narration.split()

        lines: list[str] = []
        current_words: list[str] = []
        for word in words:
            candidate = " ".join(current_words + [word])
            if not current_words or len(candidate) <= self._max_chars_per_line:
                current_words.append(word)
            else:
                lines.append(" ".join(current_words))
                current_words = [word]
        if current_words:
            lines.append(" ".join(current_words))

        cue_texts: list[str] = []
        for i in range(0, len(lines), self._max_lines_per_cue):
            group = lines[i : i + self._max_lines_per_cue]
            cue_texts.append("\n".join(group))
        return cue_texts

    def _allocate_windows(
        self, chunks: list[str], start_time: float, end_time: float
    ) -> list[tuple[float, float]]:
        """Divide ``[start_time, end_time]`` across ``chunks``
        proportionally by hybrid character/word weight (see module
        docstring), enforcing ``min_cue_seconds`` per cue where the
        scene's own duration allows it, and never crossing
        ``start_time``/``end_time``."""
        if not chunks:
            return []

        total_duration = max(end_time - start_time, 0.0)

        if len(chunks) == 1:
            return [(start_time, end_time)]

        weights = [self._weight(chunk) for chunk in chunks]
        total_weight = sum(weights) or float(len(chunks))
        raw_durations = [total_duration * (w / total_weight) for w in weights]
        durations = self._enforce_minimum_durations(raw_durations, total_duration)

        windows: list[tuple[float, float]] = []
        cursor = start_time
        for duration in durations:
            windows.append((cursor, cursor + duration))
            cursor += duration

        # Force the final window's end to exactly end_time, absorbing any
        # floating-point drift from the proportional split above rather
        # than letting it silently creep past (or short of) the scene's
        # own boundary.
        last_start, _ = windows[-1]
        windows[-1] = (last_start, end_time)
        return windows

    def _enforce_minimum_durations(
        self, durations: list[float], total_duration: float
    ) -> list[float]:
        """Redistribute ``durations`` (which already sum to
        ``total_duration``) so every entry is at least
        ``min_cue_seconds``, unless the scene itself is too short for
        that to be possible for every cue -- in which case an even split
        is used instead of violating the scene's own time boundary."""
        n = len(durations)
        if n == 0 or total_duration <= 0:
            return [0.0] * n

        min_total_needed = self._min_cue_seconds * n
        if min_total_needed > total_duration:
            even_share = total_duration / n
            return [even_share] * n

        slack = total_duration - min_total_needed
        weight_sum = sum(durations) or float(n)
        return [
            self._min_cue_seconds + slack * (duration / weight_sum)
            for duration in durations
        ]

    @staticmethod
    def _weight(text: str) -> float:
        character_count = len(text.replace("\n", " "))
        word_count = len(text.split())
        return _CHARACTER_WEIGHT * character_count + _WORD_WEIGHT * word_count
