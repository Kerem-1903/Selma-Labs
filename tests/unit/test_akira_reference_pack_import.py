from __future__ import annotations

import json
import uuid

import pytest
from PIL import Image

from core.application.services.character_reference_asset_service import (
    CharacterReferenceAssetService,
)
from core.domain.services.character_bible_validation_service import (
    CharacterBibleValidationService,
)
from core.domain.value_objects.character_identity import ReferenceView
from infrastructure.repositories.local_json_character_bible_repository import (
    LocalJsonCharacterBibleRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage
from scripts.import_akira_reference_pack import (
    AKIRA_VIEW_CROPS,
    EXPECTED_SHEET_SIZE,
    import_reference_pack,
    split_reference_sheet,
)


EXPECTED_VIEWS = (
    ReferenceView.FRONT,
    ReferenceView.THREE_QUARTER_LEFT,
    ReferenceView.PROFILE_LEFT,
    ReferenceView.BACK,
    ReferenceView.FACE_CLOSEUP,
)


def _sheet(path) -> None:
    image = Image.new("RGB", EXPECTED_SHEET_SIZE, "white")
    colors = ("red", "green", "blue", "yellow", "purple")
    for crop_box, color in zip(AKIRA_VIEW_CROPS.values(), colors, strict=True):
        image.paste(color, crop_box)
    image.save(path, format="PNG")


def test_default_multi_view_contract_matches_approved_akira_sheet():
    assert CharacterBibleValidationService.DEFAULT_REQUIRED_VIEWS == EXPECTED_VIEWS
    assert CharacterBibleValidationService().required_views == EXPECTED_VIEWS


def test_split_reference_sheet_extracts_each_named_panel(tmp_path):
    source = tmp_path / "akira-sheet.png"
    _sheet(source)

    references = split_reference_sheet(source)

    assert tuple(references) == EXPECTED_VIEWS
    for view, expected_box in AKIRA_VIEW_CROPS.items():
        output = tmp_path / f"{view.value}.png"
        output.write_bytes(references[view])
        with Image.open(output) as image:
            assert image.size == (
                expected_box[2] - expected_box[0],
                expected_box[3] - expected_box[1],
            )


def test_split_reference_sheet_rejects_an_unknown_layout(tmp_path):
    source = tmp_path / "wrong-size.png"
    Image.new("RGB", (100, 100), "white").save(source)

    with pytest.raises(ValueError, match="unexpected dimensions"):
        split_reference_sheet(source)


@pytest.mark.asyncio
async def test_real_storage_and_json_repository_round_trip_all_five_views(tmp_path):
    source = tmp_path / "akira-sheet.png"
    storage_root = tmp_path / "storage"
    bible_root = tmp_path / "bibles"
    _sheet(source)

    imported = await import_reference_pack(source, storage_root, bible_root)
    restored = await LocalJsonCharacterBibleRepository(bible_root).load("akira")
    storage = LocalFsStorage(str(storage_root))
    asset_service = CharacterReferenceAssetService(storage)

    assert imported == restored
    assert set(restored.reference_pack) == set(EXPECTED_VIEWS)
    assert CharacterBibleValidationService().validate(restored).is_complete is True

    for view in EXPECTED_VIEWS:
        reference = restored.reference_pack[view]
        uuid.UUID(reference.id)
        uuid.UUID(reference.asset_id)
        assert reference.view is view
        assert reference.revision == 1
        assert reference.content_hash
        assert reference.storage_key.startswith(
            f"characters/akira/references/{view.value.lower()}/"
        )
        assert not reference.storage_key.startswith(("/", "\\"))
        assert ":" not in reference.storage_key
        assert await storage.exists(reference.storage_key)
        assert await asset_service.load_reference(reference)

    raw_json = (bible_root / "akira.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in raw_json
    assert ":\\" not in raw_json
    envelope = json.loads(raw_json)
    assert set(envelope["character_bible"]["reference_pack"]) == {
        view.value for view in EXPECTED_VIEWS
    }

    reimported = await import_reference_pack(source, storage_root, bible_root)
    assert all(
        reference.revision == 1
        for reference in reimported.reference_pack.values()
    )
