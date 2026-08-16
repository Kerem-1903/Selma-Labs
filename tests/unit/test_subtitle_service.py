"""
Unit tests for SubtitleService.

Same no-network, fake-based principle as every other service test in this
codebase. generate() is pure (no fake needed at all); export() is tested
against a FakeStoragePort, the same pattern test_render_service.py and
test_timeline_service.py already use for StoragePort.
"""
from __future__ import annotations

import pytest

from core.application.services.subtitle_formatter import SubtitleFormatter
from core.application.services.subtitle_service import SubtitleService
from core.domain.entities.scene_plan import ScenePlan
from core.domain.exceptions import StorageError, SubtitleGenerationError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.storage_reference import StorageReference


def _scene(
    index: int = 0,
    narration: str = "A ship sails at night.",
    start_time: float = 0.0,
    end_time: float = 3.0,
) -> Scene:
    return Scene(
        index=index,
        narration=narration,
        search_keywords=["ship"],
        detected_objects=[],
        location=None,
        mood=None,
        visual_priority="high",
        start_time=start_time,
        end_time=end_time,
    )


def _scene_plan(scenes, plan_id: str | None = None) -> ScenePlan:
    plan = ScenePlan.create(
        script_id="script-1",
        voice_track_id="voice-1",
        total_duration_seconds=scenes[-1].end_time if scenes else 0.0,
        provider_used="fake",
        scenes=scenes,
    )
    if plan_id is not None:
        import dataclasses

        plan = dataclasses.replace(plan, id=plan_id)
    return plan


class FakeStorage(StoragePort):
    """In-memory StoragePort. Records every save() call; can be told to
    fail on a specific key to prove export() stops after the first
    failure."""

    def __init__(self, *, fail_on_key: str | None = None):
        self.saved: dict[str, bytes] = {}
        self.saved_content_types: dict[str, str] = {}
        self._fail_on_key = fail_on_key

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        if self._fail_on_key and key == self._fail_on_key:
            raise StorageError(f"simulated failure writing {key}")
        self.saved[key] = data
        self.saved_content_types[key] = content_type
        return StorageReference(key=key, path=f"/fake/{key}", size_bytes=len(data))


# --- generate() ---------------------------------------------------------


def test_short_scene_produces_exactly_one_cue_spanning_full_window():
    plan = _scene_plan([_scene(start_time=0.0, end_time=3.0)])
    service = SubtitleService(storage=FakeStorage())

    track = service.generate(plan)

    assert len(track.cues) == 1
    assert track.cues[0].start_time == 0.0
    assert track.cues[0].end_time == 3.0
    assert track.cues[0].scene_index == 0


def test_long_scene_produces_multiple_cues_in_order_without_overlap():
    long_narration = " ".join(f"word{i}" for i in range(40))
    plan = _scene_plan([_scene(narration=long_narration, start_time=0.0, end_time=20.0)])
    service = SubtitleService(storage=FakeStorage())

    track = service.generate(plan)

    assert len(track.cues) > 1
    for earlier, later in zip(track.cues, track.cues[1:]):
        assert earlier.end_time == later.start_time
    assert track.cues[0].start_time == 0.0
    assert track.cues[-1].end_time == 20.0


def test_cue_text_respects_max_chars_per_line_and_max_lines_per_cue():
    long_narration = " ".join(f"word{i}" for i in range(60))
    plan = _scene_plan([_scene(narration=long_narration, start_time=0.0, end_time=30.0)])
    service = SubtitleService(
        storage=FakeStorage(), max_chars_per_line=20, max_lines_per_cue=2
    )

    track = service.generate(plan)

    for cue in track.cues:
        lines = cue.text.split("\n")
        assert len(lines) <= 2
        for line in lines:
            assert len(line) <= 20


def test_a_single_very_long_word_still_gets_its_own_line():
    plan = _scene_plan([_scene(narration="Supercalifragilisticexpialidocious.", start_time=0.0, end_time=3.0)])
    service = SubtitleService(storage=FakeStorage(), max_chars_per_line=10)

    track = service.generate(plan)

    assert len(track.cues) == 1
    assert "Supercalifragilisticexpialidocious." in track.cues[0].text


def test_cue_indices_are_renumbered_across_the_whole_track_not_per_scene():
    long_narration = " ".join(f"word{i}" for i in range(30))
    scenes = [
        _scene(index=0, narration=long_narration, start_time=0.0, end_time=10.0),
        _scene(index=1, narration="Short.", start_time=10.0, end_time=12.0),
    ]
    plan = _scene_plan(scenes)
    service = SubtitleService(storage=FakeStorage())

    track = service.generate(plan)

    indices = [cue.index for cue in track.cues]
    assert indices == list(range(1, len(track.cues) + 1))


def test_cues_never_cross_a_scene_boundary():
    long_narration = " ".join(f"word{i}" for i in range(30))
    scenes = [
        _scene(index=0, narration=long_narration, start_time=0.0, end_time=8.0),
        _scene(index=1, narration="A short second scene.", start_time=8.0, end_time=11.0),
    ]
    plan = _scene_plan(scenes)
    service = SubtitleService(storage=FakeStorage())

    track = service.generate(plan)

    scene_0_cues = [c for c in track.cues if c.scene_index == 0]
    scene_1_cues = [c for c in track.cues if c.scene_index == 1]
    assert all(c.end_time <= 8.0 for c in scene_0_cues)
    assert all(c.start_time >= 8.0 for c in scene_1_cues)
    assert scene_0_cues[-1].end_time == 8.0
    assert scene_1_cues[-1].end_time == 11.0


def test_min_cue_seconds_is_enforced_when_the_scene_allows_it():
    # Heavily skewed chunk weights: one very short chunk, one very long
    # one. A naive proportional split would give the short chunk far
    # under min_cue_seconds; enforcement should lift it to the floor.
    service = SubtitleService(storage=FakeStorage(), min_cue_seconds=1.5)
    chunks = ["Hi", "word " * 40]

    windows = service._allocate_windows(chunks, start_time=0.0, end_time=10.0)

    durations = [end - start for start, end in windows]
    assert all(d >= 1.5 - 1e-9 for d in durations)
    assert windows[0][0] == 0.0
    assert windows[-1][1] == 10.0


def test_min_cue_seconds_falls_back_to_even_split_when_scene_too_short():
    # 3 chunks, min_cue_seconds=2.0 -> needs 6.0s minimum, scene is only
    # 3.0s long. Cannot satisfy the floor without crossing the scene
    # boundary, so an even split is used instead (see docstring).
    service = SubtitleService(storage=FakeStorage(), min_cue_seconds=2.0)
    chunks = ["a", "b", "c"]

    windows = service._allocate_windows(chunks, start_time=0.0, end_time=3.0)

    durations = [end - start for start, end in windows]
    assert durations == pytest.approx([1.0, 1.0, 1.0])


def test_generate_rejects_scene_plan_with_no_scenes():
    plan = _scene_plan([])
    service = SubtitleService(storage=FakeStorage())

    with pytest.raises(SubtitleGenerationError, match="no scenes"):
        service.generate(plan)


def test_generate_fails_fast_naming_scenes_with_empty_narration():
    scenes = [
        _scene(index=0, narration="Real narration.", start_time=0.0, end_time=3.0),
        _scene(index=1, narration="   ", start_time=3.0, end_time=6.0),
        _scene(index=2, narration="", start_time=6.0, end_time=9.0),
    ]
    plan = _scene_plan(scenes)
    service = SubtitleService(storage=FakeStorage())

    with pytest.raises(SubtitleGenerationError, match=r"\[1, 2\]"):
        service.generate(plan)


def test_subtitle_track_references_scene_plan_id():
    plan = _scene_plan([_scene()], plan_id="plan-abc")
    service = SubtitleService(storage=FakeStorage())

    track = service.generate(plan)

    assert track.scene_plan_id == "plan-abc"


def test_constructor_rejects_non_positive_configuration():
    with pytest.raises(ValueError):
        SubtitleService(storage=FakeStorage(), max_chars_per_line=0)
    with pytest.raises(ValueError):
        SubtitleService(storage=FakeStorage(), max_lines_per_cue=0)
    with pytest.raises(ValueError):
        SubtitleService(storage=FakeStorage(), min_cue_seconds=0)


# --- export() -------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_persists_srt_vtt_and_ass_under_base_key():
    plan = _scene_plan([_scene()])
    storage = FakeStorage()
    service = SubtitleService(storage=storage)
    track = service.generate(plan)

    references = await service.export(track, base_key="render/video-123")

    assert set(references.keys()) == {"srt", "vtt", "ass"}
    assert references["srt"].key == "render/video-123.srt"
    assert references["vtt"].key == "render/video-123.vtt"
    assert "render/video-123.srt" in storage.saved
    assert "render/video-123.vtt" in storage.saved


@pytest.mark.asyncio
async def test_export_uses_expected_content_types():
    plan = _scene_plan([_scene()])
    storage = FakeStorage()
    service = SubtitleService(storage=storage)
    track = service.generate(plan)

    await service.export(track, base_key="subtitles/track-1")

    assert storage.saved_content_types["subtitles/track-1.srt"] == "text/plain"
    assert storage.saved_content_types["subtitles/track-1.vtt"] == "text/vtt"
    assert storage.saved_content_types["subtitles/track-1.ass"] == "text/x-ssa"


def test_premium_ass_highlights_words_and_supports_contextual_emoji():
    plan = _scene_plan([_scene(narration="Ocean animals glow")])
    service = SubtitleService(storage=FakeStorage(), max_chars_per_line=24, max_lines_per_cue=1)
    track = service.generate(plan)

    ass = SubtitleFormatter.format_ass(track)

    assert ass.count("Dialogue: 0,") == 3
    assert "&H0000D7FF&" in ass
    assert "🌊" in ass


@pytest.mark.asyncio
async def test_export_persisted_srt_content_is_valid():
    plan = _scene_plan([_scene()])
    storage = FakeStorage()
    service = SubtitleService(storage=storage)
    track = service.generate(plan)

    await service.export(track, base_key="subtitles/track-1")

    srt_bytes = storage.saved["subtitles/track-1.srt"]
    assert srt_bytes.decode("utf-8").startswith("1\n")


@pytest.mark.asyncio
async def test_export_stops_after_srt_failure_and_never_writes_vtt():
    plan = _scene_plan([_scene()])
    storage = FakeStorage(fail_on_key="subtitles/track-1.srt")
    service = SubtitleService(storage=storage)
    track = service.generate(plan)

    with pytest.raises(StorageError):
        await service.export(track, base_key="subtitles/track-1")

    assert "subtitles/track-1.vtt" not in storage.saved


@pytest.mark.asyncio
async def test_export_propagates_storage_error_on_vtt_write():
    plan = _scene_plan([_scene()])
    storage = FakeStorage(fail_on_key="subtitles/track-1.vtt")
    service = SubtitleService(storage=storage)
    track = service.generate(plan)

    with pytest.raises(StorageError):
        await service.export(track, base_key="subtitles/track-1")

    # The SRT write, attempted first, still succeeded before the VTT
    # write failed.
    assert "subtitles/track-1.srt" in storage.saved
