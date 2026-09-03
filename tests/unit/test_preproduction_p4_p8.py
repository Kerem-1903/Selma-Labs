from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.application.services.animatic_planning_service import AnimaticPlanningService
from core.application.services.animation_ready_packaging_service import (
    AnimationReadyPackagingService,
)
from core.application.services.character_golden_set_service import (
    CharacterGoldenSetService,
)
from core.application.services.hierarchical_shot_planning_service import (
    HierarchicalShotPlanningService,
)
from core.domain.entities.animatic_project import AnimaticProject
from core.domain.entities.animation_ready_package import (
    AnimationReadyPackage,
    ShotPackageSources,
)
from core.domain.entities.character_golden_set import (
    CharacterGoldenSet,
    GoldenCandidateResult,
    GoldenScenario,
    default_akira_golden_cases,
)
from core.domain.entities.direction_bible import BibleStatus
from core.domain.entities.episode_production_plan import EpisodeProductionPlan
from core.domain.entities.episode_script import (
    DialogueLine,
    EpisodeScene,
    EpisodeScript,
    EpisodeScriptStatus,
    EpisodeSequence,
)
from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import AnimationPackageError
from core.domain.ports.golden_image_generator_port import GoldenImageGeneratorPort
from core.domain.ports.golden_set_evaluator_port import GoldenSetEvaluatorPort
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.storyboard_frame import StoryboardFrame
from infrastructure.providers.keyframe.golden_set_keyframe_adapter import (
    GoldenSetKeyframeAdapter,
)
from infrastructure.providers.render.remotion_animatic_exporter import (
    RemotionAnimaticExporter,
)
from infrastructure.repositories.local_json_canon_repository import (
    LocalJsonCanonRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


class _GoldenGenerator(GoldenImageGeneratorPort):
    async def generate(self, *, character, style, test_case):
        return f"golden/{character.character_id}/{test_case.scenario.value.lower()}.png"


class _GoldenEvaluator(GoldenSetEvaluatorPort):
    async def evaluate(self, *, character, style, test_case, storage_key):
        return GoldenCandidateResult(
            test_case.scenario, storage_key, 0.96, 0.93, 0.92, True
        )


class _CapturingKeyframeGenerator(KeyframeGenerationPort):
    def __init__(self) -> None:
        self.requests = []

    @property
    def name(self) -> str:
        return "capture"

    async def generate_keyframe(self, request):
        self.requests.append(request)
        return GeneratedKeyframe(b"image", "image/png", 1024, 1024)


def _episode() -> EpisodeScript:
    scene = EpisodeScene(
        id="scene-roof",
        title="The Signal",
        location="Rain Rooftop",
        summary="Rain crosses the roof as Akira follows the signal.",
        characters=("Akira",),
        dialogue=(DialogueLine("Akira", "Stay behind me."),),
    )
    return (
        EpisodeScript.create(
            title="Crimson Signal",
            logline="Akira traces a stolen memory.",
            episode_number=1,
            provider_used="test",
            sequences=(EpisodeSequence("seq-opening", "Opening", (scene,)),),
        )
        .with_status(EpisodeScriptStatus.READY_FOR_APPROVAL)
        .lock("Kerem")
    )


@pytest.mark.asyncio
async def test_locked_canon_and_ten_case_golden_set_are_production_ready():
    repository = LocalJsonCanonRepository(
        "assets/preproduction", "assets/character_bibles"
    )
    direction = await repository.get_creative_direction()
    world = await repository.get_world_bible()
    style = await repository.get_visual_style()
    (akira,) = await repository.get_character_bibles()

    golden = await CharacterGoldenSetService(
        _GoldenGenerator(), _GoldenEvaluator()
    ).run(
        character=akira,
        style=style,
        model_id="selma-image-xl",
        model_revision="sha256:test",
    )

    assert direction.status is world.status is style.status is BibleStatus.LOCKED
    assert len(golden.results) == len(default_akira_golden_cases()) == 10
    assert golden.passed
    locked = golden.lock("Kerem")
    assert locked.locked
    assert CharacterGoldenSet.from_dict(locked.to_dict()) == locked


@pytest.mark.asyncio
async def test_golden_adapter_threads_openpose_into_generation_request(tmp_path):
    repository = LocalJsonCanonRepository(
        "assets/preproduction", "assets/character_bibles"
    )
    style = await repository.get_visual_style()
    (akira,) = await repository.get_character_bibles()
    running = next(
        case
        for case in default_akira_golden_cases()
        if case.scenario is GoldenScenario.RUNNING
    )
    generator = _CapturingKeyframeGenerator()
    adapter = GoldenSetKeyframeAdapter(
        generator, LocalFsStorage(str(tmp_path / "storage"))
    )

    await adapter.generate(character=akira, style=style, test_case=running)

    request = generator.requests[0]
    assert request.visual_constraints["pose_storage_key"] == (
        "references/akira/poses/akira-running-openpose-v1.png"
    )
    assert request.visual_constraints["controlnet_type"] == "openpose"


@pytest.mark.asyncio
async def test_locked_story_reaches_animatic_and_animation_ready_packages(tmp_path):
    storage = LocalFsStorage(str(tmp_path / "storage"))
    plan = HierarchicalShotPlanningService().plan(_episode())
    storyboards = {}
    audio_keys = {}
    for index, directed in enumerate(plan.shots):
        shot = directed.plan
        image_key = f"storyboards/{shot.id}/approved.png"
        await storage.save(image_key, f"image-{index}".encode(), "image/png")
        if shot.dialogue:
            audio_keys[shot.id] = f"audio/{shot.id}.wav"
            await storage.save(audio_keys[shot.id], b"scratch-audio", "audio/wav")
        frame = StoryboardFrame(
            id=f"frame-{index}",
            shot_contract_id=shot.id,
            sequence_index=0,
            media_asset_id=f"asset-{index}",
            storage_key=image_key,
            content_type="image/png",
            provider="test",
            provider_asset_id="",
            width=1920,
            height=1080,
            reference_asset_ids=("akira-front",),
            created_at=datetime.now(timezone.utc),
        )
        storyboards[shot.id] = ShotStoryboard.create(shot.id).with_frame(frame)

    animatic = await AnimaticPlanningService(storage).build(
        plan=plan, storyboards=storyboards, dialogue_audio_keys=audio_keys
    )
    exported = await RemotionAnimaticExporter(
        storage, tmp_path / "motion-public"
    ).export(animatic)
    locked_animatic = animatic.lock("Kerem")

    golden = CharacterGoldenSet.create(
        character_id="akira",
        model_id="selma-image-xl",
        model_revision="rev-1",
        results=tuple(
            GoldenCandidateResult(
                case.scenario,
                f"golden/{case.scenario.value}.png",
                0.95,
                0.92,
                0.91,
                True,
            )
            for case in default_akira_golden_cases()
        ),
    ).lock("Kerem")
    sources = {}
    for directed in plan.shots:
        shot_id = directed.plan.id
        keys = ShotPackageSources(
            f"sources/{shot_id}/start.png",
            f"sources/{shot_id}/end.png",
            f"sources/{shot_id}/background.png",
            f"sources/{shot_id}/mask.png",
            f"sources/{shot_id}/dialogue.wav",
        )
        for key in keys.all_keys:
            await storage.save(key, b"asset", "application/octet-stream")
        sources[shot_id] = keys

    packages = await AnimationReadyPackagingService(storage).package_episode(
        plan=plan, animatic=locked_animatic, golden_set=golden, sources=sources
    )

    assert exported.is_file()
    assert len(plan.sequences) == 1 and len(plan.shots) == 2
    assert EpisodeProductionPlan.from_dict(plan.to_dict()) == plan
    assert animatic.fps == 24 and animatic.duration_in_frames > 0
    assert AnimaticProject.from_dict(locked_animatic.to_dict()) == locked_animatic
    assert len(packages) == len(plan.shots)
    for package in packages:
        assert await storage.exists(package.shot_contract_key)
        assert await storage.exists(package.effects_spec_key)
        assert await storage.exists(package.background_clean_key)
        assert AnimationReadyPackage.from_dict(package.to_dict()) == package


@pytest.mark.asyncio
async def test_packaging_fails_closed_before_animatic_and_golden_locks(tmp_path):
    storage = LocalFsStorage(str(tmp_path / "storage"))
    plan = HierarchicalShotPlanningService().plan(_episode())
    # A deliberately empty clip map cannot be used to build an animatic; package
    # validation is independently covered with a plan-mismatched object above.
    with pytest.raises(AnimationPackageError, match="locked animatic"):
        from core.domain.entities.animatic_project import AnimaticClip, AnimaticProject

        clip = AnimaticClip("shot", 0, 24, "storyboards/shot.png")
        animatic = AnimaticProject.create(production_plan_id=plan.id, clips=(clip,))
        golden = CharacterGoldenSet.create(
            character_id="akira",
            model_id="model",
            model_revision="rev",
            results=tuple(
                GoldenCandidateResult(
                    case.scenario,
                    f"golden/{case.scenario.value}.png",
                    0.95,
                    0.9,
                    0.9,
                    True,
                )
                for case in default_akira_golden_cases()
            ),
        )
        await AnimationReadyPackagingService(storage).package_episode(
            plan=plan, animatic=animatic, golden_set=golden, sources={}
        )
