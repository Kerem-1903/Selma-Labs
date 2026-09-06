from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cli.main import main
from core.application.services.character_bible_factory_service import (
    CharacterBibleFactoryService,
)
from core.application.services.series_project_service import SeriesProjectService
from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.series_project import CharacterRegistry

ROOT = Path(__file__).parents[2]
PROJECT = ROOT / "config/series/selma-anime-v1.json"


def test_selected_style_is_series_level_and_cast_starts_empty():
    project, registry = SeriesProjectService(ROOT).load(PROJECT)

    assert project.series_id == "selma-anime-v1"
    assert project.style_bible.status == "APPROVED"
    assert project.style_bible.reference_sha256 == (
        "f2af7fe8f57d035c75c07bd739ad26f0982346b9900890f4ad218b1c91931774"
    )
    assert any("non-canon" in rule for rule in project.style_bible.identity_policy)
    assert registry.members == ()


def test_series_cli_validates_without_building_generation_container(capsys):
    def forbidden_container():
        raise AssertionError("series status must not construct generation providers")

    assert (
        main(
            ["series", "status", "--project", str(PROJECT)],
            container_factory=forbidden_container,
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "VALID"
    assert payload["cast_size"] == 0
    assert payload["next_gate"] == "REGISTER_FIRST_CHARACTER"


def test_registry_rejects_duplicate_character_versions():
    member = {
        "character_id": "mira",
        "version": 1,
        "role": "lead",
        "bible_path": "assets/character_bibles/mira.json",
        "status": "DRAFT",
    }

    with pytest.raises(PreProductionValidationError, match="duplicate"):
        CharacterRegistry.from_dict(
            {
                "schema_version": 1,
                "series_id": "selma-anime-v1",
                "members": [member, member],
            }
        )


def test_series_service_rejects_style_reference_tampering(tmp_path):
    project_payload = json.loads(PROJECT.read_text(encoding="utf-8"))
    project_payload["style_bible"]["reference_asset"] = "style.png"
    project_payload["character_registry"] = "cast.json"
    project_payload["model_lock"] = "models.lock.json"
    (tmp_path / "series.json").write_text(
        json.dumps(project_payload), encoding="utf-8"
    )
    (tmp_path / "cast.json").write_text(
        json.dumps(
            {"schema_version": 1, "series_id": "selma-anime-v1", "members": []}
        ),
        encoding="utf-8",
    )
    (tmp_path / "style.png").write_bytes(b"tampered")
    (tmp_path / "models.lock.json").write_text(
        (ROOT / "models.lock.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="style reference hash mismatch"):
        SeriesProjectService(tmp_path).load(tmp_path / "series.json")


def test_registers_any_character_bible_without_a_named_default(tmp_path):
    project_payload = json.loads(PROJECT.read_text(encoding="utf-8"))
    project_payload["style_bible"]["reference_asset"] = "style.png"
    project_payload["character_registry"] = "cast.json"
    project_payload["model_lock"] = "models.lock.json"
    (tmp_path / "series.json").write_text(
        json.dumps(project_payload), encoding="utf-8"
    )
    (tmp_path / "cast.json").write_text(
        json.dumps(
            {"schema_version": 1, "series_id": "selma-anime-v1", "members": []}
        ),
        encoding="utf-8",
    )
    shutil.copyfile(
        ROOT / "assets/series/selma-anime-v1/style/approved-style-reference.png",
        tmp_path / "style.png",
    )
    shutil.copyfile(ROOT / "models.lock.json", tmp_path / "models.lock.json")
    bible = CharacterBibleFactoryService().create(
        {
            "character_id": "mira",
            "display_name": "Mira",
            "visual": {
                "eye_color": "green",
                "hair": "short silver hair",
                "facial_geometry": "angular adult face",
                "body_proportions": "athletic adult",
                "silhouette": "short jacket and wide trousers",
                "outfit": "grey courier uniform",
                "base_style": "series style",
                "immutable_marks": [],
                "color_palette": ["grey", "green"],
                "negative_prompts": ["identity drift"],
            },
            "narrative": {
                "motivation": "protect the district",
                "backstory": "former courier",
                "voice_traits": ["calm"],
            },
        }
    )
    (tmp_path / "mira.json").write_text(
        json.dumps({"character_bible": bible.to_dict()}), encoding="utf-8"
    )

    registry = SeriesProjectService(tmp_path).register_character(
        project_path=tmp_path / "series.json",
        bible_path=tmp_path / "mira.json",
        role="lead",
    )

    assert len(registry.members) == 1
    assert registry.members[0].character_id == "mira"
    persisted = json.loads((tmp_path / "cast.json").read_text(encoding="utf-8"))
    assert persisted["members"][0]["character_id"] == "mira"
