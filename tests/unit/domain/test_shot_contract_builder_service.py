from __future__ import annotations

from core.domain.entities.character_state import CharacterState
from core.domain.entities.continuity_state import ContinuityState
from core.domain.entities.script import Script
from core.domain.entities.shot_contract import ShotContract
from core.domain.services.shot_contract_builder_service import (
    ShotContractBuilderService,
)
from core.domain.value_objects.scene import Scene


def _script() -> Script:
    return Script.create(
        topic="Akira",
        full_text="Akira draws the damaged katana and advances through the rain.",
        target_duration_seconds=45,
        provider_used="test",
    )


def _scene() -> Scene:
    return Scene(
        index=2,
        narration="Akira draws the damaged katana and advances.",
        search_keywords=["akira", "katana"],
        detected_objects=["katana_01"],
        location="neon-street",
        mood="tense night",
        visual_priority="high",
        visual_job="demonstrate_mechanism",
        required_subjects=["akira", "katana_01"],
        required_actions=["draw katana", "advance carefully"],
    )


def _continuity() -> ContinuityState:
    state = ContinuityState(
        id="world-akira",
        object_states={"katana_01": "broken"},
    )
    state.update_character(
        CharacterState(
            character_id="akira",
            active_outfit_id="battle-jacket-v2",
            injuries=["left shoulder wound"],
            held_objects=["katana_01"],
            location="neon-street",
            emotion="determined",
            outfit_damage={"left_sleeve": "torn"},
        )
    )
    return state


def test_builder_pins_typed_contract_to_continuity_snapshot():
    continuity = _continuity()
    contract = ShotContractBuilderService().build(
        script=_script(),
        scene=_scene(),
        continuity_state=continuity,
        continuity_through_sequence=42,
    )

    assert contract.camera_constraints.angle == "low-angle"
    assert contract.camera_constraints.lens == "24mm"
    assert contract.action_constraints.primary_action == "draw katana"
    assert contract.action_constraints.secondary_actions == ["advance carefully"]
    assert contract.visual_constraints.lighting == "low-key"
    assert contract.visual_constraints.environment_style == "neon-street"
    assert contract.required_character_states[0].active_outfit_id == "battle-jacket-v2"
    assert contract.required_character_states[0].injuries == ["left shoulder wound"]
    assert contract.required_object_states == {"katana_01": "broken"}
    assert contract.continuity_snapshot_id == "world-akira"
    assert contract.continuity_through_sequence == 42
    assert contract.scene_index == 2
    assert not hasattr(contract, "prompt")

    continuity.world_snapshot["akira"].active_outfit_id = "future-outfit"
    assert contract.required_character_states[0].active_outfit_id == "battle-jacket-v2"


def test_built_contract_round_trips_directing_and_snapshot_metadata():
    contract = ShotContractBuilderService().build(
        script=_script(),
        scene=_scene(),
        continuity_state=_continuity(),
        continuity_through_sequence=42,
    )

    restored = ShotContract.from_dict(contract.to_dict())

    assert restored.script_id == contract.script_id
    assert restored.scene_index == 2
    assert restored.continuity_snapshot_id == "world-akira"
    assert restored.required_object_states["katana_01"] == "broken"
    assert restored.narrative_evidence.startswith("Akira draws")
