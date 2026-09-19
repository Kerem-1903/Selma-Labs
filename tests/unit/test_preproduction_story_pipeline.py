from __future__ import annotations

import asyncio
import json

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
from core.domain.exceptions import (
    ProviderTimeoutError,
    StoryApprovalError,
    StoryDevelopmentError,
)
from core.domain.ports.approval_repository_port import ApprovalRepositoryPort
from core.domain.ports.canon_repository_port import CanonRepositoryPort
from core.domain.ports.dialogue_generator_port import DialogueGeneratorPort
from core.domain.ports.story_generator_port import StoryGeneratorPort
from core.domain.ports.story_reviewer_port import StoryReviewerPort
from core.domain.value_objects.canon_validation import (
    CanonValidationReport,
    CanonViolation,
    CanonViolationCode,
)
from core.domain.value_objects.story_review import (
    ReviewSeverity,
    StoryDevelopmentResult,
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
        ScriptBreakdownService(CharacterBible.akira()).parse_episode(result.script)

    locked = await engine.approve(result, approved_by="Kerem")
    shots = ScriptBreakdownService(CharacterBible.akira()).parse_episode(locked)

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


class _StubEngine:
    """Records what the CLI hands it, without touching a model or a file."""

    def __init__(self, result):
        self._result = result
        self.approved = []

    async def review(self, script):
        return self._result

    async def approve(self, result, *, approved_by):
        locked = result.script.lock(approved_by)
        self.approved.append(locked)
        return locked


class _StubContainer:
    def __init__(self, engine):
        self.story_engine_service = engine


def _story_result(script, *, ready):
    canon_report = (
        CanonValidationReport(())
        if ready
        else CanonValidationReport(
            (
                CanonViolation(
                    CanonViolationCode.UNKNOWN_CHARACTER,
                    "Scene uses unknown character 'Ghost'.",
                    "scene-1",
                    "Ghost",
                ),
            )
        )
    )
    status = (
        EpisodeScriptStatus.READY_FOR_APPROVAL
        if ready
        else EpisodeScriptStatus.CHANGES_REQUIRED
    )
    return StoryDevelopmentResult(script.with_status(status), canon_report, ())


def _write_episode_script(path, script):
    path.write_text(
        json.dumps(
            {"schema_version": 1, "episode_script": script.to_dict()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_story_approve_writes_no_lock_when_the_gate_is_closed(tmp_path):
    """A blocked screenplay must not leave a locked artifact behind."""
    from cli.main import main

    script = _script()
    source = tmp_path / "episode.json"
    _write_episode_script(source, script)
    output = tmp_path / "locked.json"
    engine = _StubEngine(_story_result(script, ready=False))

    exit_code = main(
        [
            "story",
            "approve",
            "--input",
            str(source),
            "--approved-by",
            "LOQ",
            "--output",
            str(output),
        ],
        container_factory=lambda: _StubContainer(engine),
    )

    assert exit_code == 1
    assert not output.exists()
    assert engine.approved == []


def test_story_approve_locks_and_records_only_a_ready_screenplay(tmp_path):
    from cli.main import main

    script = _script()
    source = tmp_path / "episode.json"
    _write_episode_script(source, script)
    output = tmp_path / "locked.json"
    engine = _StubEngine(_story_result(script, ready=True))

    exit_code = main(
        [
            "story",
            "approve",
            "--input",
            str(source),
            "--approved-by",
            "LOQ",
            "--output",
            str(output),
        ],
        container_factory=lambda: _StubContainer(engine),
    )

    assert exit_code == 0
    assert len(engine.approved) == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["episode_script"]["status"] == "LOCKED"
    assert payload["episode_script"]["approved_by"] == "LOQ"
    assert payload["episode_script"]["approved_at"]
    assert payload["story_review"]["locked"] is True


@pytest.mark.asyncio
async def test_reviewer_recovers_a_severity_filed_under_the_wrong_key():
    """Captured verbatim from qwen3:8b: the severity arrived in ``code``.

    One missing key used to fail the entire review, and because the reviewers
    run concurrently that made the gate non-deterministic -- a provider defect
    dressed up as a verdict on the script.
    """
    provider = _OfflineOllamaStory(
        [
            {
                "issues": [
                    {
                        "code": "BLOCKING",
                        "message": "Forbidden phrase detected.",
                        "scene_id": "null",
                    }
                ]
            }
        ]
    )

    review = await provider.review(
        _script(), _direction().lock(), _world().lock(), (CharacterBible.akira(),)
    )

    assert not review.passed
    assert review.issues[0].severity is ReviewSeverity.BLOCKING
    assert review.issues[0].scene_id is None


@pytest.mark.asyncio
async def test_reviewer_never_drops_a_finding_that_omits_its_severity():
    provider = _OfflineOllamaStory(
        [{"issues": [{"code": "PACING", "message": "Act two repeats itself."}]}]
    )

    review = await provider.review(
        _script(), _direction().lock(), _world().lock(), (CharacterBible.akira(),)
    )

    assert review.passed
    assert len(review.issues) == 1
    assert review.issues[0].severity is ReviewSeverity.NOTE
    assert review.issues[0].message == "Act two repeats itself."


@pytest.mark.asyncio
async def test_reviewer_does_not_escalate_on_a_severity_named_in_prose():
    """Prose mentioning "blocking" must not turn a note into a blocker."""
    provider = _OfflineOllamaStory(
        [
            {
                "issues": [
                    {
                        "code": "PACING",
                        "message": "This is not a blocking issue, only a note.",
                    }
                ]
            }
        ]
    )

    review = await provider.review(
        _script(), _direction().lock(), _world().lock(), (CharacterBible.akira(),)
    )

    assert review.passed
    assert review.issues[0].severity is ReviewSeverity.NOTE


@pytest.mark.asyncio
async def test_human_story_approval_is_written_as_an_audit_artifact(tmp_path):
    locked = _script().with_status(EpisodeScriptStatus.READY_FOR_APPROVAL).lock("Kerem")
    repository = LocalJsonStoryApprovalRepository(tmp_path)

    await repository.record_story_approval(locked)

    payload = (tmp_path / f"{locked.id}.json").read_text(encoding="utf-8")
    assert '"status": "LOCKED"' in payload
    assert '"approved_by": "Kerem"' in payload


class _TimeoutOnPost:
    async def __aenter__(self):
        raise asyncio.TimeoutError

    async def __aexit__(self, *exc_info):
        return False


class _TimeoutSession:
    """Minimal aiohttp stand-in whose request never completes in time."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def post(self, url, **kwargs):
        return _TimeoutOnPost()


@pytest.mark.asyncio
async def test_ollama_story_timeout_becomes_a_domain_error(monkeypatch):
    """A slow local model must surface as a timeout, never as an empty failure.

    ``except TimeoutError`` alone does not catch ``asyncio.TimeoutError`` on
    Python 3.10, which leaked a bare timeout to the CLI with no message.
    """
    import infrastructure.providers.script.ollama_story_development_provider as module

    monkeypatch.setattr(module.aiohttp, "ClientSession", _TimeoutSession)
    provider = OllamaStoryDevelopmentProvider(model="test-model")

    with pytest.raises(ProviderTimeoutError, match="timed out"):
        await provider._complete("You are a reviewer.", {"task": "review"})


@pytest.mark.asyncio
async def test_hand_written_screenplay_is_reviewed_before_it_can_be_locked():
    """A screenplay nobody generated still reaches canon through the one gate."""
    engine, approvals = _engine()

    result = await engine.review(_script())

    assert result.ready_for_approval
    assert result.script.status is EpisodeScriptStatus.READY_FOR_APPROVAL
    assert approvals.recorded == []

    locked = await engine.approve(result, approved_by="LOQ")

    assert locked.status is EpisodeScriptStatus.LOCKED
    assert locked.approved_by == "LOQ"
    assert approvals.recorded == [locked]


@pytest.mark.asyncio
async def test_review_refuses_to_lock_a_screenplay_that_breaks_canon():
    engine, approvals = _engine()

    result = await engine.review(_script(invalid=True))

    assert result.script.status is EpisodeScriptStatus.CHANGES_REQUIRED
    assert not result.ready_for_approval
    assert result.canon_report.violations
    with pytest.raises(StoryApprovalError, match="blocking review or canon"):
        await engine.approve(result, approved_by="LOQ")
    assert approvals.recorded == []


@pytest.mark.asyncio
async def test_blocking_reviewer_finding_blocks_a_hand_written_screenplay():
    engine, _ = _engine(blocks=True)

    result = await engine.review(_script())

    assert not result.canon_report.violations
    assert result.script.status is EpisodeScriptStatus.CHANGES_REQUIRED
    assert not result.ready_for_approval


@pytest.mark.asyncio
async def test_review_requires_locked_canon_and_refuses_locked_scripts():
    unlocked, _ = _engine(locked=False)
    with pytest.raises(StoryDevelopmentError, match="locked direction"):
        await unlocked.review(_script())

    engine, _ = _engine()
    locked = _script().with_status(EpisodeScriptStatus.READY_FOR_APPROVAL).lock("Kerem")
    with pytest.raises(StoryDevelopmentError, match="cannot be reviewed again"):
        await engine.review(locked)
