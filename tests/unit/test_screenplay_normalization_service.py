from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cli.main import main
from core.application.services.screenplay_normalization_service import (
    ScreenplayNormalizationService,
)


def test_fountain_normalizer_creates_one_shared_scene_contract_per_heading():
    script = ScreenplayNormalizationService().from_fountain(
        """Title: Pilot

INT. ROOM - NIGHT

AKIRA
We move now.

EXT. STREET - DAY

Rain falls.
""",
        script_id="pilot",
    )

    assert [scene.id for scene in script.scenes] == [
        "pilot-scene-001",
        "pilot-scene-002",
    ]
    assert script.scenes[0].location == "ROOM - NIGHT"
    assert script.scenes[0].dialogue[0].speaker == "Akira"
    assert script.scenes[1].characters == ("ensemble",)


def test_episode_plan_uses_fountain_normalizer_instead_of_raw_text_parser(tmp_path):
    screenplay = tmp_path / "pilot.fountain"
    output = tmp_path / "plan.json"
    screenplay.write_text(
        """Title: Pilot

INT. ROOM - NIGHT

AKIRA
We move now.
""",
        encoding="utf-8",
    )

    assert main(
        ["episode", "plan", "--input", str(screenplay), "--output", str(output)]
    ) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    plan = payload["episode_director_plan"]
    assert plan["scene_count"] if "scene_count" in plan else len(plan["scenes"]) == 1
    assert plan["scenes"][0]["location_id"] == "room-night"


def test_episode_prepare_reuses_normalized_fountain_after_asset_generation(tmp_path):
    screenplay = tmp_path / "pilot.fountain"
    output = tmp_path / "prepare.json"
    screenplay.write_text(
        """Title: Pilot

INT. ROOM - NIGHT

AKIRA
We move now.
""",
        encoding="utf-8",
    )
    generation = SimpleNamespace(
        pose_packs={},
        background_packs={"room-night": object()},
        failures={},
        to_dict=lambda: {"status": "COMPLETED", "failures": {}, "artifacts": []},
    )
    service = SimpleNamespace(generate=AsyncMock(return_value=generation))
    container = SimpleNamespace(episode_asset_generation_service=service)

    assert main(
        [
            "episode", "prepare", "--input", str(screenplay),
            "--output", str(output), "--generate-assets",
            "--asset-mode", "PRODUCTION",
        ],
        container_factory=lambda: container,
    ) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["episode_director_plan"]["scenes"][0]["location_id"] == "room-night"
    assert payload["episode_director_plan"]["character_requirements"][0]["character_id"] == "akira"
