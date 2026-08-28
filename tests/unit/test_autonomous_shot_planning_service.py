from __future__ import annotations

import pytest

from core.application.services.autonomous_shot_planning_service import (
    AutonomousShotPlanningService,
)
from core.domain.entities.continuity_state import ContinuityState
from core.domain.entities.scene_plan import ScenePlan
from core.domain.entities.script import Script
from core.domain.entities.shot_plan import ShotPlan
from core.domain.events.continuity_event import (
    CharacterChangedOutfit,
    CharacterEnteredLocation,
    CharacterInjured,
    CharacterPickedUpObject,
    ContinuityEvent,
    ObjectBroken,
)
from core.domain.exceptions import AutonomousShotPlanningError
from core.domain.ports.continuity_repository_port import ContinuityRepositoryPort
from core.domain.value_objects.scene import Scene


class MemoryContinuityRepository(ContinuityRepositoryPort):
    def __init__(
        self,
        initial_state: ContinuityState,
        events: list[ContinuityEvent],
    ) -> None:
        self.initial_state = initial_state
        self.events = events
        self.loaded_ids: list[str] = []

    async def save(self, state: ContinuityState) -> None:
        self.initial_state = state

    async def load(self, id: str) -> ContinuityState:
        self.loaded_ids.append(id)
        return self.initial_state

    async def append_event(self, timeline_id: str, event: ContinuityEvent) -> None:
        del timeline_id
        self.events.append(event)

    async def load_events(self, timeline_id: str) -> list[ContinuityEvent]:
        self.loaded_ids.append(timeline_id)
        return list(self.events)


def _script() -> Script:
    return Script.create(
        topic="Akira",
        full_text="Akira raises the broken katana in the neon street.",
        target_duration_seconds=30,
        provider_used="test",
    )


def _scene_plan(script: Script) -> ScenePlan:
    scenes = [
        Scene(
            index=0,
            narration="Akira raises the broken katana.",
            search_keywords=["akira", "katana"],
            detected_objects=["katana_01"],
            location="neon-street",
            mood="tense",
            visual_priority="high",
            required_subjects=["akira", "katana_01"],
            required_actions=["raise katana"],
        )
    ]
    return ScenePlan.create(
        script_id=script.id,
        voice_track_id="voice-1",
        total_duration_seconds=8.0,
        provider_used="existing-scene-planner",
        scenes=scenes,
    )


def _events() -> list[ContinuityEvent]:
    return [
        CharacterEnteredLocation(
            "CharacterEnteredLocation", 1, 10, "SH_001", "akira", "neon-street"
        ),
        CharacterChangedOutfit(
            "CharacterChangedOutfit", 1, 20, "SH_002", "akira", "battle-jacket-v2"
        ),
        CharacterPickedUpObject(
            "CharacterPickedUpObject", 1, 30, "SH_003", "akira", "katana_01"
        ),
        CharacterInjured(
            "CharacterInjured", 1, 40, "SH_004", "akira", "left shoulder wound"
        ),
        ObjectBroken("ObjectBroken", 1, 50, "SH_005", "katana_01"),
    ]


@pytest.mark.asyncio
async def test_service_replays_continuity_and_builds_version_pinned_shot_plan():
    script = _script()
    repository = MemoryContinuityRepository(
        ContinuityState(id="akira-timeline"),
        _events(),
    )
    service = AutonomousShotPlanningService(repository)

    plan = await service.plan(
        script=script,
        scene_plan=_scene_plan(script),
        continuity_timeline_id="akira-timeline",
    )

    assert plan.continuity_through_sequence == 50
    assert len(plan.contracts) == 1
    contract = plan.contracts[0]
    assert contract.required_character_states[0].active_outfit_id == "battle-jacket-v2"
    assert contract.required_character_states[0].held_objects == ["katana_01"]
    assert contract.required_character_states[0].injuries == ["left shoulder wound"]
    assert contract.required_object_states == {"katana_01": "broken"}
    assert repository.loaded_ids == ["akira-timeline", "akira-timeline"]

    restored = ShotPlan.from_dict(plan.to_dict())
    assert restored.continuity_through_sequence == 50
    assert restored.contracts[0].required_object_states["katana_01"] == "broken"


@pytest.mark.asyncio
async def test_service_rejects_scene_plan_from_another_script():
    script = _script()
    other_script = _script()
    service = AutonomousShotPlanningService(
        MemoryContinuityRepository(ContinuityState(id="timeline"), [])
    )

    with pytest.raises(AutonomousShotPlanningError, match="does not belong"):
        await service.plan(
            script=script,
            scene_plan=_scene_plan(other_script),
            continuity_timeline_id="timeline",
        )


@pytest.mark.asyncio
async def test_service_rejects_ambiguous_duplicate_continuity_sequence():
    script = _script()
    duplicate = _events()[:2]
    duplicate[1] = CharacterChangedOutfit(
        "CharacterChangedOutfit", 1, 10, "SH_002", "akira", "battle-jacket-v2"
    )
    service = AutonomousShotPlanningService(
        MemoryContinuityRepository(ContinuityState(id="timeline"), duplicate)
    )

    with pytest.raises(AutonomousShotPlanningError, match="duplicate sequence"):
        await service.plan(
            script=script,
            scene_plan=_scene_plan(script),
            continuity_timeline_id="timeline",
        )
