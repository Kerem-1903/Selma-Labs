"""
Unit tests for ScenePlanningService.

Same principle as every other service test in this codebase: no network.
FakeScenePlanningProvider is a minimal in-memory implementation of
ScenePlanningPort, proving the port is genuinely swappable and that the
service's timing/validation logic is testable in isolation.
"""
from __future__ import annotations

import pytest

from core.application.services.scene_planning_service import ScenePlanningService
from core.domain.entities.script import Script
from core.domain.entities.voice_track import VoiceTrack
from core.domain.exceptions import ProviderTimeoutError, ScenePlanningError
from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.value_objects.scene import Scene


def _script(text: str = "Some narration text.") -> Script:
    return Script.create(
        topic="Titanic", full_text=text, target_duration_seconds=45, provider_used="fake"
    )


def _voice_track(duration_seconds: float = 10.0, script_id: str | None = None) -> VoiceTrack:
    return VoiceTrack.create(
        script_id=script_id,
        duration_seconds=duration_seconds,
        provider="fake",
        voice_name="fake-voice",
        sample_rate=44100,
        file_path="/fake/audio.mp3",
    )


def _raw_scene(narration: str, keywords=None, index: int = 99) -> Scene:
    # index=99 on purpose in most fixtures: proves the service re-derives
    # index from list order rather than trusting whatever a provider sends.
    return Scene(
        index=index,
        narration=narration,
        search_keywords=keywords if keywords is not None else ["keyword"],
        detected_objects=["object"],
        location="a place",
        mood="hope",
        visual_priority="high",
    )


class FakeScenePlanningProvider(ScenePlanningPort):
    """In-memory ScenePlanningPort implementation for tests."""

    def __init__(self, scenes=None, raises=None, identity: str = "fake:model"):
        self._scenes = scenes if scenes is not None else [_raw_scene("Some narration text.")]
        self._raises = raises
        self._identity = identity
        self.last_narration_text: str | None = None

    @property
    def provider_identity(self) -> str:
        return self._identity

    async def plan_scenes(self, narration_text: str) -> list[Scene]:
        self.last_narration_text = narration_text
        if self._raises:
            raise self._raises
        return self._scenes


@pytest.mark.asyncio
async def test_plan_returns_scene_plan_with_provider_identity_and_ids():
    script = _script()
    voice_track = _voice_track(duration_seconds=10.0, script_id=script.id)
    provider = FakeScenePlanningProvider(identity="anthropic:claude-sonnet-4-5")
    service = ScenePlanningService(provider)

    scene_plan = await service.plan(script, voice_track)

    assert scene_plan.script_id == script.id
    assert scene_plan.voice_track_id == voice_track.audio_id
    assert scene_plan.provider_used == "anthropic:claude-sonnet-4-5"
    assert scene_plan.total_duration_seconds == 10.0


@pytest.mark.asyncio
async def test_single_scene_spans_the_entire_duration():
    provider = FakeScenePlanningProvider(scenes=[_raw_scene("The whole narration.")])
    service = ScenePlanningService(provider)

    scene_plan = await service.plan(_script(), _voice_track(duration_seconds=12.0))

    assert len(scene_plan.scenes) == 1
    scene = scene_plan.scenes[0]
    assert scene.start_time == 0.0
    assert scene.end_time == 12.0
    assert scene.index == 0


@pytest.mark.asyncio
async def test_multi_scene_timing_proportional_to_word_count():
    # 2 words then 8 words -> 20%/80% split of a 10s track.
    scenes = [
        _raw_scene("one two"),
        _raw_scene("one two three four five six seven eight"),
    ]
    provider = FakeScenePlanningProvider(scenes=scenes)
    service = ScenePlanningService(provider)

    scene_plan = await service.plan(_script(), _voice_track(duration_seconds=10.0))

    assert scene_plan.scenes[0].start_time == 0.0
    assert scene_plan.scenes[0].end_time == 2.0
    assert scene_plan.scenes[1].start_time == 2.0
    assert scene_plan.scenes[1].end_time == 10.0  # snapped to total duration


@pytest.mark.asyncio
async def test_scenes_are_reindexed_regardless_of_provider_supplied_index():
    scenes = [_raw_scene("First scene.", index=7), _raw_scene("Second scene.", index=3)]
    provider = FakeScenePlanningProvider(scenes=scenes)
    service = ScenePlanningService(provider)

    scene_plan = await service.plan(_script(), _voice_track())

    assert scene_plan.scenes[0].index == 0
    assert scene_plan.scenes[1].index == 1


@pytest.mark.asyncio
async def test_passes_script_narration_text_to_provider():
    provider = FakeScenePlanningProvider()
    service = ScenePlanningService(provider)

    await service.plan(_script("Exact narration text."), _voice_track())

    assert provider.last_narration_text == "Exact narration text."


@pytest.mark.asyncio
async def test_rejects_empty_script_narration():
    service = ScenePlanningService(FakeScenePlanningProvider())

    with pytest.raises(ScenePlanningError, match="no narration text"):
        await service.plan(_script("   "), _voice_track())


@pytest.mark.asyncio
async def test_rejects_invalid_voice_track_duration():
    service = ScenePlanningService(FakeScenePlanningProvider())

    with pytest.raises(ScenePlanningError, match="invalid duration_seconds"):
        await service.plan(_script(), _voice_track(duration_seconds=0))


@pytest.mark.asyncio
async def test_raises_when_provider_returns_no_scenes():
    provider = FakeScenePlanningProvider(scenes=[])
    service = ScenePlanningService(provider)

    with pytest.raises(ScenePlanningError, match="no scenes"):
        await service.plan(_script(), _voice_track())


@pytest.mark.asyncio
async def test_raises_when_a_scene_is_missing_narration():
    provider = FakeScenePlanningProvider(scenes=[_raw_scene("   ")])
    service = ScenePlanningService(provider)

    with pytest.raises(ScenePlanningError, match="missing narration"):
        await service.plan(_script(), _voice_track())


@pytest.mark.asyncio
async def test_raises_when_a_scene_has_no_search_keywords():
    provider = FakeScenePlanningProvider(scenes=[_raw_scene("Some text.", keywords=[])])
    service = ScenePlanningService(provider)

    with pytest.raises(ScenePlanningError, match="no search_keywords"):
        await service.plan(_script(), _voice_track())


@pytest.mark.asyncio
async def test_propagates_provider_errors_unchanged():
    provider = FakeScenePlanningProvider(raises=ProviderTimeoutError("simulated timeout"))
    service = ScenePlanningService(provider)

    with pytest.raises(ProviderTimeoutError, match="simulated timeout"):
        await service.plan(_script(), _voice_track())
