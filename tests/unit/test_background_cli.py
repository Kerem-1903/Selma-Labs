from __future__ import annotations

import json

from cli.main import main


def test_background_init_and_plan_do_not_construct_runtime_container(tmp_path):
    brief = tmp_path / "brief.json"
    bible = tmp_path / "bible.json"
    plan = tmp_path / "plan.json"
    brief.write_text(
        json.dumps(
            {
                "name": "Sky Bridge",
                "description": "A suspended bridge above the clouds",
                "immutable_geometry": ["one central arch"],
                "architecture": ["white stone"],
                "palette": ["white", "blue"],
                "lighting_sources": ["sunlight"],
                "weather_options": ["clear"],
                "style": "hand-painted anime background",
            }
        ),
        encoding="utf-8",
    )

    def forbidden_container():
        raise AssertionError("Planning must not construct provider infrastructure.")

    assert (
        main(
            ["background", "init", "--brief", str(brief), "--output", str(bible)],
            container_factory=forbidden_container,
        )
        == 0
    )
    assert (
        main(
            ["background", "plan", "--input", str(bible), "--output", str(plan)],
            container_factory=forbidden_container,
        )
        == 0
    )

    payload = json.loads(plan.read_text(encoding="utf-8"))
    assert payload["location_id"] == "sky-bridge"
    assert len(payload["recipes"]) == 12


def test_background_approval_explicitly_locks_complete_pack(tmp_path):
    bible = tmp_path / "bible.json"
    manifest = tmp_path / "manifest.json"
    approved = tmp_path / "approved.json"
    bible.write_text(
        json.dumps(
            {
                "location_bible": {
                    "location_id": "sky-bridge",
                    "name": "Sky Bridge",
                    "description": "A bridge above clouds",
                    "immutable_geometry": ["central arch"],
                    "architecture": ["white stone"],
                    "palette": ["white", "blue"],
                    "lighting_sources": ["sunlight"],
                    "interaction_points": [],
                    "weather_options": ["clear"],
                    "forbidden_elements": [],
                    "style": "anime background",
                    "locked": False,
                }
            }
        ),
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "location_id": "sky-bridge",
                "candidates": [
                    {
                        "storage_key": f"background-candidates/sky-bridge/source/{i}.png",
                        "quality": {"passed": True},
                    }
                    for i in range(12)
                ],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "background",
                "approve",
                "--input",
                str(bible),
                "--manifest",
                str(manifest),
                "--approved-by",
                "art-director",
                "--output",
                str(approved),
            ]
        )
        == 0
    )

    result = json.loads(approved.read_text(encoding="utf-8"))
    assert result["location_bible"]["locked"] is True
    assert result["approval"]["approved_by"] == "art-director"
