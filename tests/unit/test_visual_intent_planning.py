from __future__ import annotations

import pytest

from core.application.services.scene_planning_service import ScenePlanningService
from core.domain.exceptions import ScenePlanningError
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.narrative_contract import NarrativeBeat
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.word_timing import WordTiming


class _UnusedSceneProvider:
    """The music-first method must not invoke the legacy narration provider."""

    provider_identity = "fake:scene"

    async def plan_scenes(self, narration_text: str):  # pragma: no cover - contract guard
        raise AssertionError("Legacy provider must not be called.")


def _highlight(score: float) -> SelectedHighlight:
    return SelectedHighlight(
        audio_asset_id="audio-1",
        start_ms=0,
        end_ms=15_000,
        score=score,
        selector_used="fake:energy",
        hook_type="chorus",
        rationale="test",
    )


def _cue(text: str = "Dancing through city lights") -> SubtitleCue:
    words = [
        WordTiming(word, index * 300, (index + 1) * 300, 0.99)
        for index, word in enumerate(text.split())
    ]
    return SubtitleCue.from_words(words)


def test_high_energy_hook_creates_fast_paced_intents():
    service = ScenePlanningService(_UnusedSceneProvider())

    intents = service.plan_visual_intents(_highlight(0.85), [_cue()])

    assert intents[0].primary_keyword == "dancing"
    assert intents[0].mood == "energetic"
    assert intents[0].motion_type == "fast-paced"
    assert intents[0].forbidden_concepts == ("text", "logo", "watermark", "face")


def test_low_energy_hook_creates_slow_motion_intents():
    service = ScenePlanningService(_UnusedSceneProvider())

    intents = service.plan_visual_intents(_highlight(0.25), [_cue("Falling rain")])

    assert intents[0].mood == "melancholic"
    assert intents[0].motion_type == "slow-motion"


def test_visual_intents_require_caption_anchor():
    service = ScenePlanningService(_UnusedSceneProvider())

    with pytest.raises(ScenePlanningError, match="subtitle cues"):
        service.plan_visual_intents(_highlight(0.85), [])


def test_visual_intents_enforce_rapid_cut_density_for_a_long_hook():
    service = ScenePlanningService(_UnusedSceneProvider())
    highlight = SelectedHighlight(
        audio_asset_id="audio-1",
        start_ms=0,
        end_ms=32_000,
        score=0.85,
        selector_used="fake:energy",
        hook_type="chorus",
        rationale="test",
    )

    intents = service.plan_visual_intents(highlight, [_cue("Ocean mystery")])

    assert len(intents) >= 10  # Dense opening plus sub-3.5s editorial beats.
    assert all(intent.motion_type == "fast-paced" for intent in intents)
    assert intents[0].start_ms == 0
    assert intents[-1].end_ms == 32_000
    assert all(
        current.end_ms == following.start_ms
        for current, following in zip(intents, intents[1:])
    )
    assert max(intent.duration_ms for intent in intents) <= 3_200


def test_storyboard_assigns_hook_payoff_and_varied_shot_grammar():
    service = ScenePlanningService(_UnusedSceneProvider())

    intents = service.plan_visual_intents(
        _highlight(0.55),
        [_cue("Octopus hearts pump blue blood")],
    )

    assert intents[0].narrative_role == "hook"
    assert intents[-1].narrative_role == "payoff"
    assert intents[0].shot_type == "macro-close-up"
    assert len({intent.shot_type for intent in intents[:5]}) == 5
    assert intents[0].duration_ms == 1_200
    assert "macro close up" in intents[0].search_query
    assert intents[0].secondary_keywords


def test_topic_storyboard_turns_anatomy_and_mechanism_into_explanatory_jobs():
    service = ScenePlanningService(_UnusedSceneProvider())
    highlight = SelectedHighlight(
        audio_asset_id="audio-1",
        start_ms=0,
        end_ms=6_000,
        score=0.55,
        selector_used="fake",
        hook_type="narration",
        rationale="test",
    )
    cues = [
        SubtitleCue.from_words(
            [
                WordTiming("Ahtapotun", 0, 450, 0.99),
                WordTiming("üç", 460, 700, 0.99),
                WordTiming("kalbi", 710, 1_200, 0.99),
                WordTiming("var.", 1_210, 1_450, 0.99),
            ]
        ),
        SubtitleCue.from_words(
            [
                WordTiming("Çünkü", 1_500, 1_850, 0.99),
                WordTiming("iki", 1_860, 2_050, 0.99),
                WordTiming("kalp", 2_060, 2_350, 0.99),
                WordTiming("kanı", 2_360, 2_650, 0.99),
                WordTiming("gönderir.", 2_660, 3_400, 0.99),
            ]
        ),
        SubtitleCue.from_words(
            [
                WordTiming("Böylece", 3_500, 3_950, 0.99),
                WordTiming("üçüncü", 3_960, 4_350, 0.99),
                WordTiming("kalp", 4_360, 4_650, 0.99),
                WordTiming("vücudu", 4_660, 5_050, 0.99),
                WordTiming("besler.", 5_060, 5_800, 0.99),
            ]
        ),
    ]
    beats = (
        NarrativeBeat(0, "hook", "Ahtapotun üç kalbi var.", "opens", False),
        NarrativeBeat(
            1,
            "evidence",
            "Çünkü iki kalp kanı solungaçlara gönderir.",
            "mechanism",
            True,
        ),
        NarrativeBeat(
            2,
            "payoff",
            "Böylece üçüncü kalp vücudu besler.",
            "payoff",
            False,
        ),
    )

    intents = service.plan_visual_intents(
        highlight,
        cues,
        narrative_beats=beats,
        visual_anchor="Ahtapotların neden üç kalbi var?",
    )

    assert all(intent.required_subjects for intent in intents)
    assert any(intent.visual_job == "demonstrate_mechanism" for intent in intents)
    assert any(intent.explanatory_required for intent in intents)
    assert all(
        intent.explanation_mode == "hybrid" and intent.overlay_labels
        for intent in intents
        if intent.explanatory_required
    )
    assert "ray" in intents[0].forbidden_dominant_subjects
    spoken_boundaries = {
        boundary
        for cue in cues
        for boundary in (
            cue.start_ms,
            cue.end_ms,
            *(word.end_ms for word in cue.words),
        )
    }
    assert all(intent.end_ms in spoken_boundaries for intent in intents[:-1])


def test_explanatory_visual_intent_cannot_use_stock_alone():
    with pytest.raises(ValueError, match="cannot rely on stock footage alone"):
        from core.domain.value_objects.visual_intent import VisualIntent

        VisualIntent(
            "octopus",
            "reflective",
            "steady",
            explanatory_required=True,
            explanation_mode="stock",
            overlay_labels=("3 HEARTS",),
        )
