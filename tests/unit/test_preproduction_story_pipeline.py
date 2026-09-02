from __future__ import annotations

import pytest

from core.application.services.canon_validation_service import CanonValidationService
from core.application.services.script_breakdown_service import ScriptBreakdownService
from core.application.services.story_engine_service import StoryEngineService
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.direction_bible import (
    BibleStatus,
    CreativeDirectionBible,
    LocationDefinition,
    VisualStyleBible,
    WorldBible,
    WorldRule,
)
from core.domain.entities.episode_script import (
    AbilityUse,
    DialogueLine,
    EpisodeScene,
    EpisodeScript,
    EpisodeScriptStatus,
    EpisodeSequence,
    StoryBrief,
)
from core.domain.exceptions import StoryApprovalError, StoryDevelopmentError
from core.domain.ports.approval_repository_port import ApprovalRepositoryPort
from core.domain.ports.canon_repository_port import CanonRepositoryPort
from core.domain.ports.dialogue_generator_port import DialogueGeneratorPort
from core.domain.ports.story_generator_port import StoryGeneratorPort
from core.domain.ports.story_reviewer_port import StoryReviewerPort
from core.domain.value_objects.canon_validation import CanonViolationCode
from core.domain.value_objects.story_review import (
    ReviewSeverity,
    StoryReviewIssue,
    StoryReviewReport,
)
from infrastructure.providers.script.ollama_story_development_provider import (
    OllamaStoryDevelopmentProvider,
)
from infrastructure.repositories.local_json_story_approval_repository import (
    LocalJsonStoryApprovalRepository,
)


def _direction():
    return CreativeDirectionBible.create(
        title="Crimson Silence",
        version=1,
        genre="original cinematic shonen",
        target_audience="16+",
        narrative_tone=("restrained", "tense"),
        visual_identity="Dark city, amber highlights, hard cel shading.",
        originality_guardrails=("Bleach",),
    )


def _world():
    return WorldBible.create(
        name="Kizil Sehir",
        version=1,
        premise="A private security network regulates memory.",
        locations=(LocationDefinition("roof", "Rain Rooftop", ("Cati",)),),
        rules=(WorldRule("death-final", "Death is irreversible.", ("resurrection",)),),
    )


def _script(*, invalid: bool = False):
    scene = EpisodeScene(
        id="scene-1",
        title="Signal",
        location="Moon" if invalid else "Rain Rooftop",
        summary="Akira abandons civilians during a resurrection."
        if invalid
        else "Akira protects civilians while tracing a forbidden signal.",
        characters=("Akira", "Stranger") if invalid else ("Akira",),
        dialogue=(
            DialogueLine("Akira", "I give up.")
            if invalid
            else DialogueLine("Akira", "Stay behind me."),
        ),
        ability_uses=(
            AbilityUse("Akira", "Infinite Fire")
            if invalid
            else AbilityUse("Akira", "Crimson Arc"),
        ),
    )
    return EpisodeScript.create(
        title="Bleach Signal" if invalid else "The Signal",
        logline="Akira traces a forbidden signal.",
        episode_number=1,
        provider_used="fake",
        sequences=(EpisodeSequence("seq-1", "Opening", (scene,)),),
    )


def test_bibles_and_episode_are_immutable_and_round_trip():
    visual = VisualStyleBible.create(
        name="Crimson Silence",
        version=1,
        palette=("#151318", "#7A1F2B"),
        line_language="Controlled ink lines.",
        shading_language="Two-step hard shadows.",
        camera_language="Still anticipation and short bursts.",
    )
    script = _script().with_status(EpisodeScriptStatus.READY_FOR_APPROVAL).lock("Kerem")

    assert _direction().lock().status is BibleStatus.LOCKED
    assert _world().lock().status is BibleStatus.LOCKED
    assert visual.lock().status is BibleStatus.LOCKED
    assert EpisodeScript.from_dict(script.to_dict()) == script


def test_canon_validator_reports_all_deterministic_failures():
    report = CanonValidationService().validate(
        _script(invalid=True),
        _direction().lock(),
        _world().lock(),
        (CharacterBible.akira(),),
    )
    codes = {violation.code for violation in report.violations}

    assert {
        CanonViolationCode.UNKNOWN_LOCATION,
        CanonViolationCode.UNKNOWN_CHARACTER,
        CanonViolationCode.WORLD_RULE_VIOLATION,
        CanonViolationCode.CHARACTER_MOTIVATION_CONFLICT,
        CanonViolationCode.CHARACTER_VOICE_MISMATCH,
        CanonViolationCode.UNAUTHORIZED_POWER,
        CanonViolationCode.STYLE_IMITATION_RISK,
    } <= codes


class _Canon(CanonRepositoryPort):
    def __init__(self, locked=True):
        self.direction = _direction().lock() if locked else _direction()
        self.world = _world().lock() if locked else _world()

    async def get_creative_direction(self):
        return self.direction

    async def get_world_bible(self):
        return self.world

    async def get_visual_style(self):
        raise NotImplementedError

    async def get_character_bibles(self):
        return (CharacterBible.akira(),)


class _Writer(StoryGeneratorPort):
    async def generate_episode(
        self, brief, creative_direction, world_bible, character_bibles
    ):
        return _script()


class _Dialogue(DialogueGeneratorPort):
    async def refine_dialogue(self, script, character_bibles):
        return script


class _Reviewer(StoryReviewerPort):
    def __init__(self, blocks=False):
        self.blocks = blocks

    async def review(self, script, creative_direction, world_bible, character_bibles):
        issues = (
            (
                StoryReviewIssue(
                    "WEAK_PAYOFF", "Strengthen payoff.", ReviewSeverity.BLOCKING
                ),
            )
            if self.blocks
            else ()
        )
        return StoryReviewReport("editor", issues)


class _Approvals(ApprovalRepositoryPort):
    def __init__(self):
        self.recorded = []

    async def record_story_approval(self, script):
        self.recorded.append(script)


def _engine(*, locked=True, blocks=False):
    approvals = _Approvals()
    return StoryEngineService(
        story_generator=_Writer(),
        dialogue_generator=_Dialogue(),
        reviewers=(_Reviewer(blocks),),
        canon_repository=_Canon(locked),
        approval_repository=approvals,
    ), approvals


@pytest.mark.asyncio
async def test_story_requires_reviews_then_human_approval_before_breakdown():
    engine, approvals = _engine()
    result = await engine.develop(StoryBrief("Akira hears a signal.", 1, 180))
    with pytest.raises(StoryApprovalError, match="human-approved"):
        ScriptBreakdownService().parse_episode(result.script)

    locked = await engine.approve(result, approved_by="Kerem")
    shots = ScriptBreakdownService().parse_episode(locked)

    assert locked.status is EpisodeScriptStatus.LOCKED
    assert approvals.recorded == [locked]
    assert shots and all(not shot.keyframe_approved for shot in shots)


@pytest.mark.asyncio
async def test_story_pipeline_fails_closed_for_blocking_review_and_draft_canon():
    engine, _ = _engine(blocks=True)
    result = await engine.develop(StoryBrief("Akira hears a signal.", 1, 180))
    assert result.script.status is EpisodeScriptStatus.CHANGES_REQUIRED
    with pytest.raises(StoryApprovalError):
        await engine.approve(result, approved_by="Kerem")

    unlocked_engine, _ = _engine(locked=False)
    with pytest.raises(StoryDevelopmentError, match="locked direction"):
        await unlocked_engine.develop(StoryBrief("Akira hears a signal.", 1, 180))


class _OfflineOllamaStory(OllamaStoryDevelopmentProvider):
    def __init__(self, responses):
        super().__init__(model="test-model")
        self.responses = list(responses)

    async def _complete(self, system, user_payload):
        assert system and user_payload
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_local_structured_story_adapter_writes_refines_and_reviews():
    episode_json = {
        "title": "Signal",
        "logline": "Akira hears a signal.",
        "sequences": [
            {
                "id": "seq-1",
                "title": "Opening",
                "scenes": [
                    {
                        "id": "scene-1",
                        "title": "Rain",
                        "location": "Rain Rooftop",
                        "summary": "Akira traces the signal.",
                        "characters": ["Akira"],
                        "dialogue": [{"speaker": "Akira", "text": "I hear it."}],
                        "ability_uses": [],
                    }
                ],
            }
        ],
    }
    refined_json = {**episode_json}
    refined_json["sequences"] = [
        {
            **episode_json["sequences"][0],
            "scenes": [
                {
                    **episode_json["sequences"][0]["scenes"][0],
                    "dialogue": [{"speaker": "Akira", "text": "The signal is close."}],
                }
            ],
        }
    ]
    provider = _OfflineOllamaStory(
        [
            episode_json,
            refined_json,
            {
                "issues": [
                    {
                        "code": "TIGHTEN",
                        "message": "Trim pause.",
                        "severity": "WARNING",
                        "scene_id": "scene-1",
                    }
                ]
            },
        ]
    )
    script = await provider.generate_episode(
        StoryBrief("Akira hears a signal.", 1, 180),
        _direction().lock(),
        _world().lock(),
        (CharacterBible.akira(),),
    )
    refined = await provider.refine_dialogue(script, (CharacterBible.akira(),))
    review = await provider.review(
        refined, _direction().lock(), _world().lock(), (CharacterBible.akira(),)
    )

    assert refined.scenes[0].dialogue[0].text == "The signal is close."
    assert review.passed and review.issues[0].severity is ReviewSeverity.WARNING


@pytest.mark.asyncio
async def test_human_story_approval_is_written_as_an_audit_artifact(tmp_path):
    locked = _script().with_status(EpisodeScriptStatus.READY_FOR_APPROVAL).lock("Kerem")
    repository = LocalJsonStoryApprovalRepository(tmp_path)

    await repository.record_story_approval(locked)

    payload = (tmp_path / f"{locked.id}.json").read_text(encoding="utf-8")
    assert '"status": "LOCKED"' in payload
    assert '"approved_by": "Kerem"' in payload
