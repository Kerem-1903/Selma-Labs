from __future__ import annotations

import json

from cli.main import main
from config.container import AnimationContainer, create_container
from config.settings import Settings
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
    assert container["animation_orchestrator_service"] is container.animation_orchestrator_service


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
    source.write_text("AKIRA: I remember this place.\nThe light flickers.", encoding="utf-8")

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
