from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from cli.main import main
from config.container import AnimationContainer, create_container
from config.settings import Settings
from core.application.services.view_framing_gate import ViewFramingGate
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.character_rig import RigSpecification
from core.domain.entities.episode_script import (
    DialogueLine,
    EpisodeScene,
    EpisodeScript,
    EpisodeScriptStatus,
    EpisodeSequence,
)
from core.domain.ports.character_rig_port import RigValidationReport
from infrastructure.storage.local_fs_storage import LocalFsStorage


class FakeComfyClient:
    pass


def test_container_wires_canonical_character_and_services(tmp_path):
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path),
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
    )
    storage = LocalFsStorage(str(tmp_path))

    container = create_container(
        settings=settings,
        storage=storage,
        comfyui_client=FakeComfyClient(),
    )

    assert isinstance(container, AnimationContainer)
    assert container.character_bible is None
    assert container["script_breakdown_service"] is container.script_breakdown_service
    assert (
        container["animation_orchestrator_service"]
        is container.animation_orchestrator_service
    )
    assert container.keyframe_generation_service._human_review_required is True
    assert isinstance(
        container.character_onboarding_service._framing_gate, ViewFramingGate
    )
    assert container.character_onboarding_service._style_refine is False


def test_container_can_enable_character_style_refinement(tmp_path):
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path),
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
        character_style_refine_enabled=True,
    )

    container = create_container(settings=settings)

    assert container.character_onboarding_service._style_refine is True


def test_container_allows_explicit_legacy_keyframe_flow(tmp_path):
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path),
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
    )

    container = create_container(
        settings=settings,
        comfyui_client=FakeComfyClient(),
        human_review_required=False,
    )

    assert container.keyframe_generation_service._human_review_required is False


def test_character_lora_defaults_are_identity_safe():
    settings = Settings(_env_file=None)

    assert settings.comfyui_character_lora_strength_model == 0.45
    assert settings.comfyui_character_lora_strength_clip == 0.0


def test_cli_shows_character_without_constructing_provider_container(capsys):
    def forbidden_container():
        raise AssertionError("character show must not construct provider adapters")

    exit_code = main(
        [
            "character",
            "show",
            "--input",
            str(Path(__file__).parents[2] / "assets/character_bibles/akira.json"),
        ],
        container_factory=forbidden_container,
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["character_id"] == "akira"
    assert "akira_girl" in payload["prompt_fragments"]


def test_cli_creates_generic_character_onboarding_plan(tmp_path, capsys):
    source = tmp_path / "character.json"
    output = tmp_path / "onboarding.json"
    source.write_text(
        json.dumps({"character_bible": CharacterBible.akira().to_dict()}),
        encoding="utf-8",
    )

    assert (
        main(["character", "plan", "--input", str(source), "--output", str(output)])
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["training_count"] == 20
    assert payload["holdout_count"] == 3
    assert payload["trigger_token"] == "selma_akira_v1"
    assert len(payload["recipes"]) == 23
    assert Path(capsys.readouterr().out.strip()) == output.resolve()


def test_cli_generates_and_approves_canonical_design_from_brief(tmp_path, capsys):
    brief_path = tmp_path / "brief.json"
    manifest_path = tmp_path / "designs.json"
    approval_path = tmp_path / "canonical-approval.json"
    turnaround_path = tmp_path / "turnaround.json"
    asset_root = tmp_path / "assets"
    brief_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Mira",
                "concept": "Underground courier who manipulates sound",
                "hair": "black bob with one red lock",
                "outfit": "cropped courier jacket",
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path / "runtime"),
        keyframe_storage_root_dir=str(asset_root),
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
    )

    def factory():
        return create_container(settings=settings)

    # Seed canonical pose templates into the keyframe storage so the
    # fail-closed pose conditioning for directional views can resolve.
    pose_root = asset_root / "characters" / "_pose_templates"
    pose_root.mkdir(parents=True, exist_ok=True)
    for _pose_name in (
        "pose_front.png",
        "pose_back_v5.png",
        "pose_profile_left.png",
        "pose_profile_right.png",
    ):
        (pose_root / _pose_name).write_bytes(
            (
                Path(__file__).parents[2] / "assets" / "pose_templates" / _pose_name
            ).read_bytes()
        )

    assert (
        main(
            [
                "character",
                "create",
                "--brief",
                str(brief_path),
                "--manifest",
                str(manifest_path),
            ],
            container_factory=factory,
        )
        == 0
    )
    capsys.readouterr()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected_key = manifest["candidates"][0]["storage_key"]

    assert (
        main(
            [
                "character",
                "approve-design",
                "--brief",
                str(brief_path),
                "--manifest",
                str(manifest_path),
                "--candidate-key",
                selected_key,
                "--approved-by",
                "Kerem",
                "--output",
                str(approval_path),
            ],
            container_factory=factory,
        )
        == 0
    )

    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    assert approval["approved_by"] == "Kerem"
    assert (asset_root / "characters/mira/v1/canonical_source.png").is_file()
    assert (asset_root / "characters/mira/v1/face_anchor.png").is_file()
    assert (asset_root / "characters/mira/v1/fullbody_anchor.png").is_file()
    assert (asset_root / "characters/mira/v1/canonical-approval.json").is_file()

    assert (
        main(
            [
                "character",
                "turnaround",
                "--brief",
                str(brief_path),
                "--approval",
                str(approval_path),
                "--manifest",
                str(turnaround_path),
            ],
            container_factory=factory,
        )
        == 0
    )
    turnaround = json.loads(turnaround_path.read_text(encoding="utf-8"))
    assert [view["view"] for view in turnaround["views"]] == [
        "FACE_CLOSEUP",
        "FRONT",
        "PROFILE_LEFT",
        "PROFILE_RIGHT",
        "THREE_QUARTER_LEFT",
        "THREE_QUARTER_RIGHT",
        "BACK",
    ]
    assert turnaround["next_gate"] == "PENDING_HUMAN_REVIEW"
    assert (asset_root / "characters/mira/v1/contact-sheets/views.png").is_file()
    production_manifest = json.loads(
        (asset_root / "characters/mira/v1/manifest.json").read_text(encoding="utf-8")
    )
    assert production_manifest["status"] == "PENDING_HUMAN_REVIEW"
    assert len(production_manifest["assets"]) == 10
    assert all("qc_metrics" in item for item in production_manifest["assets"])
    capsys.readouterr()

    acceptance_dir = tmp_path / "acceptance"
    acceptance_dir.mkdir(parents=True, exist_ok=True)
    acceptance_path = acceptance_dir / "mira-v1.json"
    acceptance_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "character_id": "mira",
                "character_version": 1,
                "brief_hash": manifest["brief_hash"],
                "blocking_policy": "All checks must pass before view-pack approval.",
                "automatic_checks": ["exactly_one_person"],
                "human_checks": [
                    {
                        "id": "same_facial_identity",
                        "label": "same facial identity in all seven views",
                    },
                    {
                        "id": "bag_character_right_never_mirrored",
                        "label": "messenger bag stays on character-right hip",
                    },
                ],
                "required_evidence": [
                    "canonical-approval.json",
                    "face_anchor.png",
                    "fullbody_anchor.png",
                    "view-pack.json",
                    "contact-sheets/views.png",
                    "manifest.json",
                ],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "character",
                "approve-view-pack",
                "--character",
                "mira",
                "--version",
                "v1",
                "--approved-by",
                "Kerem",
                "--acceptance",
                str(acceptance_path),
                "--check",
                "same_facial_identity",
                "--check",
                "bag_character_right_never_mirrored",
            ],
            container_factory=factory,
        )
        == 0
    )
    view_approval = json.loads(capsys.readouterr().out)
    assert view_approval["human_approved"] is True
    assert len(view_approval["view_hashes"]) == 7
    assert len(view_approval["human_checks"]) == 2
    assert len(view_approval["verified_evidence"]) >= 5
    assert len(view_approval["acceptance_sha256"]) == 64
    assert (asset_root / "characters/mira/v1/view-pack-approval.json").is_file()


def test_cli_approve_view_pack_fails_closed_without_signed_acceptance(tmp_path, capsys):
    brief_path = tmp_path / "brief.json"
    manifest_path = tmp_path / "designs.json"
    approval_path = tmp_path / "canonical-approval.json"
    turnaround_path = tmp_path / "turnaround.json"
    asset_root = tmp_path / "assets"
    brief_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Mira",
                "concept": "Underground courier who manipulates sound",
                "hair": "black bob with one red lock",
                "outfit": "cropped courier jacket",
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path / "runtime"),
        keyframe_storage_root_dir=str(asset_root),
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
    )

    def factory():
        return create_container(settings=settings)

    # Seed canonical pose templates into the keyframe storage so the
    # fail-closed pose conditioning for directional views can resolve.
    pose_root = asset_root / "characters" / "_pose_templates"
    pose_root.mkdir(parents=True, exist_ok=True)
    for _pose_name in (
        "pose_front.png",
        "pose_back_v5.png",
        "pose_profile_left.png",
        "pose_profile_right.png",
    ):
        (pose_root / _pose_name).write_bytes(
            (
                Path(__file__).parents[2] / "assets" / "pose_templates" / _pose_name
            ).read_bytes()
        )

    assert (
        main(
            [
                "character",
                "create",
                "--brief",
                str(brief_path),
                "--manifest",
                str(manifest_path),
            ],
            container_factory=factory,
        )
        == 0
    )
    capsys.readouterr()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected_key = manifest["candidates"][0]["storage_key"]
    assert (
        main(
            [
                "character",
                "approve-design",
                "--brief",
                str(brief_path),
                "--manifest",
                str(manifest_path),
                "--candidate-key",
                selected_key,
                "--approved-by",
                "Kerem",
                "--output",
                str(approval_path),
            ],
            container_factory=factory,
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "character",
                "turnaround",
                "--brief",
                str(brief_path),
                "--approval",
                str(approval_path),
                "--manifest",
                str(turnaround_path),
            ],
            container_factory=factory,
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "character",
                "approve-view-pack",
                "--character",
                "mira",
                "--version",
                "v1",
                "--approved-by",
                "Kerem",
            ],
            container_factory=factory,
        )
        != 0
    )
    assert not (asset_root / "characters/mira/v1/view-pack-approval.json").is_file()


def test_cli_breakdown_writes_unapproved_shot_plan(tmp_path):
    source = tmp_path / "story.txt"
    output = tmp_path / "plan.json"
    source.write_text(
        "AKIRA: I remember this place.\nThe light flickers.", encoding="utf-8"
    )

    exit_code = main(
        [
            "script",
            "breakdown",
            "--input",
            str(source),
            "--character-bible",
            str(Path(__file__).parents[2] / "assets/character_bibles/akira.json"),
            "--script-id",
            "broken-record",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(payload["shots"]) == 2
    assert all(shot["keyframe_approved"] is False for shot in payload["shots"])


def test_preproduction_status_and_locked_episode_plan_commands(tmp_path, capsys):
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path / "storage"),
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
    )

    def factory():
        return create_container(
            settings=settings,
            storage=LocalFsStorage(str(tmp_path / "storage")),
            comfyui_client=FakeComfyClient(),
            character_bible=CharacterBible.akira(),
        )

    assert main(["preproduction", "status"], container_factory=factory) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["story_canon_locked"] is True
    assert status["visual_style_locked"] is True
    assert status["next_gate"] == "GOLDEN_SET"

    scene = EpisodeScene(
        "scene-1",
        "Signal",
        "Rain Rooftop",
        "Akira follows the signal.",
        ("Akira",),
        (DialogueLine("Akira", "Stay behind me."),),
    )
    script = (
        EpisodeScript.create(
            title="Signal",
            logline="Akira hears a stolen memory.",
            episode_number=1,
            provider_used="test",
            sequences=(EpisodeSequence("seq-1", "Opening", (scene,)),),
        )
        .with_status(EpisodeScriptStatus.READY_FOR_APPROVAL)
        .lock("Kerem")
    )
    source = tmp_path / "episode.json"
    output = tmp_path / "plan.json"
    source.write_text(json.dumps(script.to_dict()), encoding="utf-8")

    assert (
        main(
            [
                "preproduction",
                "plan",
                "--input",
                str(source),
                "--character-id",
                "akira",
                "--output",
                str(output),
            ],
            container_factory=factory,
        )
        == 0
    )
    plan = json.loads(output.read_text(encoding="utf-8"))
    shots = plan["episode_production_plan"]["sequences"][0]["scenes"][0]["shots"]
    assert len(shots) == 2
    assert {shot["plan"]["character_state"]["character_id"] for shot in shots} == {
        "akira"
    }


def test_preproduction_plan_refuses_an_unresolvable_character_bible(tmp_path, capsys):
    """The plan command used to be reachable only from tests.

    Nothing in the CLI ever handed a Character Bible to the container, so the
    breakdown service always refused. The identity is now selected explicitly
    and resolved from canon, and an unresolvable one must refuse instead of
    silently planning every shot against whatever bible happened to be wired.
    """
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path / "storage"),
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
    )

    def factory():
        # Deliberately no character_bible: this is how production builds it.
        return create_container(
            settings=settings,
            storage=LocalFsStorage(str(tmp_path / "storage")),
            comfyui_client=FakeComfyClient(),
        )

    scene = EpisodeScene(
        "scene-1",
        "Signal",
        "Rain Rooftop",
        "Akira follows the signal.",
        ("Akira",),
        (DialogueLine("Akira", "Stay behind me."),),
    )
    script = (
        EpisodeScript.create(
            title="Signal",
            logline="Akira hears a stolen memory.",
            episode_number=1,
            provider_used="test",
            sequences=(EpisodeSequence("seq-1", "Opening", (scene,)),),
        )
        .with_status(EpisodeScriptStatus.READY_FOR_APPROVAL)
        .lock("Kerem")
    )
    source = tmp_path / "episode.json"
    output = tmp_path / "plan.json"
    source.write_text(json.dumps(script.to_dict()), encoding="utf-8")

    assert (
        main(
            [
                "preproduction",
                "plan",
                "--input",
                str(source),
                "--character-id",
                "no-such-character",
                "--output",
                str(output),
            ],
            container_factory=factory,
        )
        == 1
    )
    assert "was not found exactly once" in capsys.readouterr().err
    assert not output.exists()


def test_preproduction_plan_refuses_a_draft_script(tmp_path, capsys):
    """An unlocked screenplay must never reach the shot hierarchy."""
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path / "storage"),
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
    )

    def factory():
        return create_container(settings=settings, storage=LocalFsStorage(str(tmp_path / "storage")))

    scene = EpisodeScene(
        "scene-1",
        "Signal",
        "Rain Rooftop",
        "Akira follows the signal.",
        ("Akira",),
        (DialogueLine("Akira", "Stay behind me."),),
    )
    script = EpisodeScript.create(
        title="Signal",
        logline="Akira hears a stolen memory.",
        episode_number=1,
        provider_used="test",
        sequences=(EpisodeSequence("seq-1", "Opening", (scene,)),),
    )
    source = tmp_path / "draft.json"
    output = tmp_path / "plan.json"
    source.write_text(json.dumps(script.to_dict()), encoding="utf-8")

    assert (
        main(
            [
                "preproduction",
                "plan",
                "--input",
                str(source),
                "--character-id",
                "akira",
                "--output",
                str(output),
            ],
            container_factory=factory,
        )
        == 1
    )
    assert "locked episode script" in capsys.readouterr().err
    assert not output.exists()


def test_preproduction_golden_set_blocks_without_approved_reference_pack(
    tmp_path, capsys
):
    output = tmp_path / "akira-golden-set.json"
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path / "runtime"),
        preproduction_asset_root=str(tmp_path / "assets"),
        keyframe_generation_provider="fake",
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
        golden_marker_gate_enabled=False,
    )

    def factory():
        return create_container(settings=settings)

    assert (
        main(
            [
                "preproduction",
                "golden-set",
                "--model-id",
                "offline-smoke",
                "--model-revision",
                "v1",
                "--output",
                str(output),
            ],
            container_factory=factory,
        )
        == 1
    )
    assert "reference pack is incomplete" in capsys.readouterr().err
    assert not output.exists()
    assert list((tmp_path / "assets").rglob("*.png")) == []


def test_rig_validate_returns_nonzero_for_invalid_rig(capsys):
    adapter = AsyncMock()
    adapter.validate_rig.return_value = RigValidationReport(
        is_valid=False,
        specification=RigSpecification(
            has_ik_arm_l=False,
            has_ik_arm_r=False,
            has_ik_leg_l=False,
            has_ik_leg_r=False,
            has_fk_arm_l=False,
            has_fk_arm_r=False,
            has_fk_leg_l=False,
            has_fk_leg_r=False,
            has_secondary_hair=False,
            has_secondary_jacket=False,
        ),
        errors=("No armature found.",),
    )

    with patch(
        "infrastructure.providers.blender.blender_rig_adapter.BlenderRigAdapter",
        return_value=adapter,
    ):
        exit_code = main(["rig", "validate", "--model", "missing.blend"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["is_valid"] is False
    assert "No armature found." in payload["errors"]


def _prepared_turnaround_workspace(tmp_path):
    """Create a brief plus an approved canonical design, ready for a turnaround."""
    brief_path = tmp_path / "brief.json"
    manifest_path = tmp_path / "designs.json"
    approval_path = tmp_path / "canonical-approval.json"
    asset_root = tmp_path / "assets"
    brief_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Mira",
                "concept": "Underground courier who manipulates sound",
                "hair": "black bob with one red lock",
                "outfit": "cropped courier jacket",
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        storage_root_dir=str(tmp_path / "runtime"),
        keyframe_storage_root_dir=str(asset_root),
        keyframe_candidate_db_path=str(tmp_path / "candidates.db"),
    )

    def factory():
        return create_container(settings=settings)

    pose_root = asset_root / "characters" / "_pose_templates"
    pose_root.mkdir(parents=True, exist_ok=True)
    for pose_name in (
        "pose_front.png",
        "pose_back_v5.png",
        "pose_profile_left.png",
        "pose_profile_right.png",
    ):
        (pose_root / pose_name).write_bytes(
            (Path(__file__).parents[2] / "assets" / "pose_templates" / pose_name).read_bytes()
        )

    assert (
        main(
            ["character", "create", "--brief", str(brief_path), "--manifest", str(manifest_path)],
            container_factory=factory,
        )
        == 0
    )
    selected_key = json.loads(manifest_path.read_text(encoding="utf-8"))["candidates"][0][
        "storage_key"
    ]
    assert (
        main(
            [
                "character",
                "approve-design",
                "--brief",
                str(brief_path),
                "--manifest",
                str(manifest_path),
                "--candidate-key",
                selected_key,
                "--approved-by",
                "Kerem",
                "--output",
                str(approval_path),
            ],
            container_factory=factory,
        )
        == 0
    )
    return brief_path, approval_path, asset_root, factory


def _turnaround_fixture(tmp_path):
    """Prepare a workspace plus the brief/approval objects a run needs."""
    from cli.character_asset_commands import _load_object
    from cli.main import _load_character_creation_brief
    from core.domain.value_objects.character_design import CharacterCanonicalApproval

    brief_path, approval_path, asset_root, factory = _prepared_turnaround_workspace(
        tmp_path
    )
    return (
        _load_character_creation_brief(brief_path),
        CharacterCanonicalApproval.from_dict(_load_object(approval_path)),
        asset_root,
        factory,
    )


def test_cli_turnaround_forwards_the_seed_sweep(tmp_path, capsys):
    """`--seeds` used to be parsed and then dropped on the floor."""
    _brief_path, approval_path, asset_root, factory = _prepared_turnaround_workspace(
        tmp_path
    )
    container = factory()
    observed: dict[str, object] = {}
    original = container.character_view_pack_generation_service.generate_canonical_views

    async def spy(
        brief,
        approval,
        *,
        output_prefix="characters",
        view_candidate_count=None,
        rerender_views=None,
    ):
        observed["count"] = view_candidate_count
        observed["rerender_views"] = rerender_views
        return await original(
            brief,
            approval,
            output_prefix=output_prefix,
            view_candidate_count=view_candidate_count,
            rerender_views=rerender_views,
        )

    container.character_view_pack_generation_service.generate_canonical_views = spy

    assert (
        main(
            [
                "character",
                "turnaround",
                "--brief",
                str(_brief_path),
                "--approval",
                str(approval_path),
                "--manifest",
                str(tmp_path / "turnaround.json"),
                "--seeds",
                "3",
            ],
            container_factory=lambda: container,
        )
        == 0
    )
    capsys.readouterr()

    assert observed["count"] == 3
    # A full turnaround must not accidentally enter targeted re-render mode.
    assert observed["rerender_views"] in (None, ())
    assert (asset_root / "characters/mira/v1/view-pack.json").is_file()


def test_cli_turnaround_forwards_the_targeted_rerender_views(tmp_path, capsys):
    """`--view` must reach the service, or the flag would silently do nothing."""
    brief_path, approval_path, asset_root, factory = _prepared_turnaround_workspace(
        tmp_path
    )
    container = factory()
    observed: dict[str, object] = {}
    original = container.character_view_pack_generation_service.generate_canonical_views

    async def spy(
        brief,
        approval,
        *,
        output_prefix="characters",
        view_candidate_count=None,
        rerender_views=None,
    ):
        observed["rerender_views"] = rerender_views
        return await original(
            brief,
            approval,
            output_prefix=output_prefix,
            view_candidate_count=view_candidate_count,
            rerender_views=rerender_views,
        )

    container.character_view_pack_generation_service.generate_canonical_views = spy

    # A targeted re-render needs a pack to draw into, so draw one first.
    assert (
        main(
            [
                "character",
                "turnaround",
                "--brief",
                str(brief_path),
                "--approval",
                str(approval_path),
                "--manifest",
                str(tmp_path / "turnaround.json"),
            ],
            container_factory=lambda: container,
        )
        == 0
    )
    capsys.readouterr()
    observed.clear()

    assert (
        main(
            [
                "character",
                "turnaround",
                "--brief",
                str(brief_path),
                "--approval",
                str(approval_path),
                "--manifest",
                str(tmp_path / "turnaround.json"),
                "--view",
                "three_quarter_right",
                "--view",
                "profile_right",
            ],
            container_factory=lambda: container,
        )
        == 0
    )
    capsys.readouterr()

    # The CLI forwards what the operator typed; the service is where view names
    # are folded to their canonical spelling.
    assert observed["rerender_views"] == ["three_quarter_right", "profile_right"]
    pack = json.loads(
        (asset_root / "characters/mira/v1/view-pack.json").read_text(encoding="utf-8")
    )
    superseded = {
        item["view"]
        for item in pack["quarantined"]
        if item["reasons"] == ["superseded_by_targeted_rerender"]
    }
    assert superseded == {"THREE_QUARTER_RIGHT", "PROFILE_RIGHT"}


def test_turnaround_seed_sweep_renders_every_seed(tmp_path):
    """The service, not just the CLI, must honour the seed count."""

    def renders(tmp: Path, seeds: int) -> dict[str, int]:
        tmp.mkdir(parents=True, exist_ok=True)
        brief, approval, _asset_root, factory = _turnaround_fixture(tmp)
        service = factory().character_view_pack_generation_service
        tally: dict[str, int] = {}
        original = service._generator.generate_keyframe

        async def counting(request):
            key = str(
                request.visual_constraints.get("view")
                or request.shot_contract_id
                or "unknown"
            )
            tally[key] = tally.get(key, 0) + 1
            return await original(request)

        service._generator.generate_keyframe = counting
        asyncio.run(
            service.generate_canonical_views(
                brief, approval, view_candidate_count=seeds
            )
        )
        return tally

    single = renders(tmp_path / "one", 1)
    triple = renders(tmp_path / "three", 3)

    assert sum(single.values()) > 0
    assert sum(triple.values()) == 3 * sum(single.values())
    # The views that are copied from an approved artifact by contract have
    # nothing to choose between; sweeping them would burn renders on output that
    # is thrown away, so they are never swept and never drawn at all.
    assert "FACE_CLOSEUP" not in triple
    assert "FRONT" not in triple


def _unlocked_brief(character_id: str = "elias") -> dict:
    return {
        "character_id": character_id,
        "display_name": "Elias",
        "visual": {
            "eye_color": "grey",
            "hair": "dark brown, swept back",
            "facial_geometry": "angular face with a straight nose",
            "body_proportions": "average adult proportions",
            "silhouette": "grey medical coat over dark trousers",
            "outfit": "grey medical coat and dark trousers",
            "base_style": "clean cinematic anime character design",
        },
        "narrative": {
            "motivation": "Prove what the infection does before it erases everyone he knows.",
            "backstory": (
                "A researcher who stopped sleeping on day four, when his own "
                "reflection stopped feeling like someone he knew."
            ),
        },
    }


def test_narrative_lock_records_the_approver_without_claiming_visual_readiness(
    tmp_path,
):
    """Narrative canon must be lockable without rendering a single frame."""
    from core.application.services.character_bible_factory_service import (
        CharacterBibleFactoryService,
    )

    bible = CharacterBibleFactoryService().create(_unlocked_brief())
    assert bible.narrative_profile is not None
    assert bible.narrative_profile.locked is False
    source = tmp_path / "elias.json"
    source.write_text(
        json.dumps(
            {"schema_version": 1, "character_bible": bible.to_dict()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "elias-locked.json"
    receipt = tmp_path / "elias-receipt.json"

    exit_code = main(
        [
            "character",
            "lock-narrative",
            "--input",
            str(source),
            "--approved-by",
            "LOQ",
            "--output",
            str(output),
            "--receipt",
            str(receipt),
        ]
    )

    assert exit_code == 0
    locked = json.loads(output.read_text(encoding="utf-8"))["character_bible"]
    assert locked["narrative_profile"]["locked"] is True
    recorded = json.loads(receipt.read_text(encoding="utf-8"))
    assert recorded["character_id"] == "elias"
    assert recorded["approved_by"] == "LOQ"
    assert recorded["narrative_locked"] is True
    assert recorded["narrative_hash"]
    assert recorded["visual_readiness_claimed"] is False


def test_narrative_lock_refuses_to_silently_relock_locked_canon(tmp_path):
    source = tmp_path / "locked.json"
    output = tmp_path / "never-written.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "character_bible": CharacterBible.akira().to_dict(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "character",
            "lock-narrative",
            "--input",
            str(source),
            "--approved-by",
            "LOQ",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert not output.exists()
