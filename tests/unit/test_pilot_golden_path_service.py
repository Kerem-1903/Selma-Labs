from __future__ import annotations

import json

from cli.main import main
from core.application.services.pilot_golden_path_service import PilotGoldenPathService


def test_default_pilot_is_ready_for_the_first_golden_path_gate():
    report = PilotGoldenPathService().check_text(
        PilotGoldenPathService.DEFAULT_FOUNTAIN
    )

    assert report.status == "READY"
    assert report.fps == 24
    assert 6 <= report.shot_count <= 10
    assert 30 <= report.duration_seconds <= 60
    assert set(report.characters) == {"akira", "kaito"}
    assert len(report.locations) == 1
    assert report.failures == ()


def test_pilot_check_blocks_unapproved_characters_and_multiple_locations():
    screenplay = PilotGoldenPathService.DEFAULT_FOUNTAIN.replace(
        "INT. SESSIZ SİNYAL ODASI - NIGHT",
        "INT. SESSIZ SİNYAL ODASI - NIGHT\n\nNOVA\nI should not be here.",
    ).replace(
        "KAITO\nThen someone wanted it found, but only after the district went quiet.",
        "KAITO\nThen someone wanted it found, but only after the district went quiet.\n\nEXT. SECOND LOCATION - NIGHT\n\nAKIRA\nWe moved.",
    )

    report = PilotGoldenPathService().check_text(screenplay)

    assert report.status == "BLOCKED"
    assert "no_unapproved_characters" in report.failures
    assert "one_location" in report.failures


def test_pilot_init_and_check_cli_write_reviewable_artifacts(tmp_path):
    screenplay = tmp_path / "pilot.fountain"
    report_path = tmp_path / "pilot-check.json"

    assert main(["pilot", "init", "--output", str(screenplay)]) == 0
    assert screenplay.is_file()
    assert (
        main(
            [
                "pilot",
                "check",
                "--input",
                str(screenplay),
                "--output",
                str(report_path),
            ]
        )
        == 0
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "READY"
    assert report["shot_count"] == 9


def test_pilot_smoke_plan_is_exactly_five_seconds_at_24fps():
    from cli.pilot_commands import _five_second_anchor_smoke_plan

    plan = _five_second_anchor_smoke_plan(
        akira_image="characters/akira/v5/canonical_source.png",
        kaito_image="characters/kaito/v5/canonical_source.png",
    )

    assert plan.fps == 24
    assert plan.duration_frames == 120
    assert plan.total_duration_seconds == 5.0
    assert [shot.duration_frames for shot in plan.scenes[0].shots] == [60, 60]
    assert plan.metadata["smoke_kind"] == "ANCHOR_SMOKE_NOT_VIEW_PACK_APPROVED"


def test_pilot_smoke_cli_writes_anchor_smoke_result_without_render(tmp_path):
    from cli.main import main

    storage_root = tmp_path / "storage"
    for character in ("akira", "kaito"):
        source = storage_root / f"characters/{character}/v5/canonical_source.png"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"png-placeholder")
    output = tmp_path / "smoke.json"

    assert main(
        [
            "pilot",
            "smoke",
            "--storage-root",
            str(storage_root),
            "--output",
            str(output),
        ]
    ) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "READY_FOR_REVIEW"
    assert payload["smoke_kind"] == "ANCHOR_SMOKE_NOT_VIEW_PACK_APPROVED"
    assert payload["animatic"]["animatic_project"]["duration_in_frames"] == 120



def test_pilot_plan_requires_readiness_and_writes_episode_plan(tmp_path):
    screenplay = tmp_path / "pilot.fountain"
    plan_path = tmp_path / "pilot-plan.json"
    screenplay.write_text(
        PilotGoldenPathService.DEFAULT_FOUNTAIN,
        encoding="utf-8",
    )

    assert (
        main(
            [
                "pilot",
                "plan",
                "--input",
                str(screenplay),
                "--output",
                str(plan_path),
            ]
        )
        == 0
    )

    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    plan = payload["episode_director_plan"]
    assert plan["fps"] == 24
    assert plan["episode_id"] == "pilot"
    assert len(plan["scenes"]) == 1
    assert len(plan["scenes"][0]["shots"]) == 9
