"""
Unit tests for ClaudeScenePlanningProvider.

No network involved: ``_parse_response``, ``_strip_code_fence``, and
``_normalize_priority`` are pure functions/classmethods tested directly
against sample text, the same way test_pexels_provider.py tests
PexelsProvider's pure mapping logic without hitting the network.
"""
from __future__ import annotations

import pytest

from core.domain.exceptions import ProviderAuthError, ScenePlanningError
from infrastructure.providers.scene_planning.claude_scene_planning_provider import (
    ClaudeScenePlanningProvider,
)

VALID_JSON = """[
    {"narration": "The Titanic leaves Southampton.", "search_keywords": ["titanic", "harbor"],
     "detected_objects": ["ship"], "location": "harbor", "mood": "hope",
     "visual_priority": "high"},
    {"narration": "It strikes an iceberg at night.", "search_keywords": ["iceberg", "ocean"],
     "detected_objects": ["iceberg", "ship"], "location": "open ocean", "mood": "tension",
     "visual_priority": "high"}
]"""


def test_parse_response_maps_valid_json_to_scenes():
    scenes = ClaudeScenePlanningProvider._parse_response(VALID_JSON)

    assert len(scenes) == 2
    assert scenes[0].index == 0
    assert scenes[0].narration == "The Titanic leaves Southampton."
    assert scenes[0].search_keywords == ["titanic", "harbor"]
    assert scenes[0].detected_objects == ["ship"]
    assert scenes[0].location == "harbor"
    assert scenes[0].mood == "hope"
    assert scenes[0].visual_priority == "high"
    assert scenes[1].index == 1


def test_parse_response_strips_markdown_code_fence():
    fenced = f"```json\n{VALID_JSON}\n```"
    scenes = ClaudeScenePlanningProvider._parse_response(fenced)
    assert len(scenes) == 2


def test_parse_response_defaults_missing_location_and_mood_to_none():
    raw = '[{"narration": "Text.", "search_keywords": ["kw"]}]'
    scenes = ClaudeScenePlanningProvider._parse_response(raw)
    assert scenes[0].location is None
    assert scenes[0].mood is None
    assert scenes[0].detected_objects == []


def test_parse_response_defaults_invalid_priority_to_medium():
    raw = '[{"narration": "Text.", "search_keywords": ["kw"], "visual_priority": "urgent!!"}]'
    scenes = ClaudeScenePlanningProvider._parse_response(raw)
    assert scenes[0].visual_priority == "medium"


def test_parse_response_accepts_valid_priority_case_insensitively():
    raw = '[{"narration": "Text.", "search_keywords": ["kw"], "visual_priority": "LOW"}]'
    scenes = ClaudeScenePlanningProvider._parse_response(raw)
    assert scenes[0].visual_priority == "low"


def test_parse_response_raises_on_invalid_json():
    with pytest.raises(ScenePlanningError, match="wasn't valid JSON"):
        ClaudeScenePlanningProvider._parse_response("not json at all {")


def test_parse_response_raises_when_not_a_list():
    with pytest.raises(ScenePlanningError, match="not a list"):
        ClaudeScenePlanningProvider._parse_response('{"narration": "Text."}')


def test_parse_response_raises_when_scene_missing_narration():
    raw = '[{"search_keywords": ["kw"]}]'
    with pytest.raises(ScenePlanningError, match="missing required 'narration'"):
        ClaudeScenePlanningProvider._parse_response(raw)


def test_parse_response_raises_when_array_element_is_not_an_object():
    raw = '["just a string", "another"]'
    with pytest.raises(ScenePlanningError, match="missing required 'narration'"):
        ClaudeScenePlanningProvider._parse_response(raw)


def test_strip_code_fence_removes_fence_and_language_tag():
    fenced = "```json\n[1, 2, 3]\n```"
    assert ClaudeScenePlanningProvider._strip_code_fence(fenced) == "[1, 2, 3]"


def test_strip_code_fence_is_noop_without_fence():
    plain = "[1, 2, 3]"
    assert ClaudeScenePlanningProvider._strip_code_fence(plain) == plain


def test_normalize_priority_valid_values():
    assert ClaudeScenePlanningProvider._normalize_priority("high") == "high"
    assert ClaudeScenePlanningProvider._normalize_priority("Medium") == "medium"
    assert ClaudeScenePlanningProvider._normalize_priority("LOW") == "low"


def test_normalize_priority_falls_back_to_medium():
    assert ClaudeScenePlanningProvider._normalize_priority("urgent") == "medium"
    assert ClaudeScenePlanningProvider._normalize_priority(None) == "medium"
    assert ClaudeScenePlanningProvider._normalize_priority(42) == "medium"


def test_constructor_requires_api_key():
    with pytest.raises(ProviderAuthError):
        ClaudeScenePlanningProvider(api_key="", model="claude-sonnet-4-5")


def test_provider_identity_reflects_configured_model():
    provider = ClaudeScenePlanningProvider(api_key="fake-key", model="claude-sonnet-4-5")
    assert provider.provider_identity == "anthropic:claude-sonnet-4-5"
