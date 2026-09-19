from __future__ import annotations

import pytest

from core.application.services.episode_director_service import EpisodeDirectorService
from core.domain.exceptions import ProviderError, ScenePlanningError
from core.domain.value_objects.episode_director_decision import EpisodeSceneDecision
from infrastructure.providers.episode_director.claude_episode_director_provider import (
    ClaudeEpisodeDirectorProvider,
)


class _Provider:
    provider_identity = "fake:director"

    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error

    async def decide(self, screenplay_text):
        if self.error:
            raise self.error
        return self.decision


def _decision(scene_id="episode-001-scene-001"):
    return EpisodeSceneDecision(
        scene_id=scene_id,
        purpose="show the character choosing to move",
        story_beat="conflict",
        emotional_intent="urgent",
        character_actions={"akira": "raises her hand toward the signal"},
        pose_preferences={"akira": "PROFILE_LEFT"},
        shot_sizes=("wide", "close_up"),
        background_direction="wet rooftop with a pulsing red signal",
    )


@pytest.mark.asyncio
async def test_structured_provider_decision_controls_episode_plan():
    plan = await EpisodeDirectorService().plan_with_provider(
        "SCENE: Rooftop\nAKIRA: We move now.",
        _Provider(type("Decision", (), {"decisions": (_decision(),)})()),
    )
    assert plan.decision_mode == "LLM"
    assert plan.provider == "fake:director"
    assert plan.scenes[0].story_beat == "conflict"
    assert plan.scenes[0].scene_purpose.startswith("show the character")
    assert plan.scenes[0].shots[0].character_pose_id == "PROFILE_LEFT"
    assert "wet rooftop" in plan.scenes[0].shots[0].background_prompt


@pytest.mark.asyncio
async def test_provider_failure_falls_back_without_breaking_offline_plan():
    plan = await EpisodeDirectorService().plan_with_provider(
        "SCENE: Rooftop\nAKIRA: We wait.",
        _Provider(error=ProviderError("offline")),
    )
    assert plan.decision_mode == "RULE_FALLBACK"
    assert plan.provider == "rules:episode-director-v1"
    assert any("fallback used" in warning for warning in plan.warnings)
    assert plan.timeline


@pytest.mark.asyncio
async def test_provider_decisions_must_cover_every_scene_and_fall_back():
    plan = await EpisodeDirectorService().plan_with_provider(
        "SCENE: Rooftop\nAKIRA: Wait.\n\nSCENE: Station\nAKIRA: Run.",
        _Provider(type("Decision", (), {"decisions": (_decision(),)})()),
    )
    assert plan.decision_mode == "RULE_FALLBACK"
    assert any("fallback used" in warning for warning in plan.warnings)


def test_claude_adapter_parses_and_validates_structured_output():
    payload = '{"decisions":[{"scene_id":"s1","purpose":"reveal the threat","story_beat":"reveal","emotional_intent":"alarmed","character_actions":{"akira":"turns"},"pose_preferences":{"akira":"PROFILE_LEFT"},"shot_sizes":["medium"],"background_direction":"fog"}],"rationale":"test"}'
    decision = ClaudeEpisodeDirectorProvider._parse_response(payload)
    assert decision.decisions[0].story_beat == "reveal"
    assert decision.decisions[0].pose_preferences["akira"] == "PROFILE_LEFT"


def test_claude_adapter_rejects_invalid_structured_output():
    with pytest.raises(ScenePlanningError):
        ClaudeEpisodeDirectorProvider._parse_response('{"decisions":[{"scene_id":"s1"}]}')
