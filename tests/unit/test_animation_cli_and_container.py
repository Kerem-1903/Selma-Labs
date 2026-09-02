from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from cli.main import main
from config.container import AnimationContainer, create_container
from config.settings import Settings
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
    assert container.character_bible.trigger_prompt == "akira_girl"
    assert container["script_breakdown_service"] is container.script_breakdown_service
    assert (
        container["animation_orchestrator_service"]
        is container.animation_orchestrator_service
    )


def test_cli_shows_character_without_constructing_provider_container(capsys):
    def forbidden_container():
        raise AssertionError("character show must not construct provider adapters")

    exit_code = main(
        ["character", "show"],
        container_factory=forbidden_container,
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["character_id"] == "akira"
    assert "akira_girl" in payload["prompt_fragments"]


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
            ["preproduction", "plan", "--input", str(source), "--output", str(output)],
            container_factory=factory,
        )
        == 0
    )
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert (
        len(plan["episode_production_plan"]["sequences"][0]["scenes"][0]["shots"]) == 2
    )


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
