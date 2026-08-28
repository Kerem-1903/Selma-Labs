from __future__ import annotations

import json

import pytest

from core.domain.entities.character_bible import CharacterBible
from core.domain.exceptions import CharacterBibleNotFoundError, CharacterBibleStateError
from core.domain.value_objects.character_identity import IdentityConstraints
from core.domain.value_objects.style_profile import StyleProfile
from infrastructure.repositories.local_json_character_bible_repository import (
    LocalJsonCharacterBibleRepository,
)


def _bible(character_id: str = "akira") -> CharacterBible:
    return CharacterBible(
        character_id=character_id,
        identity_constraints=IdentityConstraints(
            eye_color="Brown",
            hair="Black spiky",
            facial_geometry="Angular",
            body_proportions="Athletic",
            silhouette="Tall",
        ),
        style_profile=StyleProfile(base_style="Anime"),
    )


@pytest.mark.asyncio
async def test_repository_round_trip_uses_versioned_envelope_and_atomic_file(tmp_path):
    repository = LocalJsonCharacterBibleRepository(tmp_path / "bibles")

    await repository.save(_bible())
    restored = await repository.load("akira")

    path = tmp_path / "bibles" / "akira.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["schema_version"] == 1
    assert envelope["character_bible"]["character_id"] == "akira"
    assert restored.identity_constraints.hair == "Black spiky"
    assert list((tmp_path / "bibles").glob("*.tmp")) == []


@pytest.mark.asyncio
async def test_repository_missing_character_raises_typed_error(tmp_path):
    repository = LocalJsonCharacterBibleRepository(tmp_path)

    with pytest.raises(CharacterBibleNotFoundError):
        await repository.load("akira")


@pytest.mark.asyncio
async def test_repository_rejects_corrupt_or_unknown_schema(tmp_path):
    repository = LocalJsonCharacterBibleRepository(tmp_path)
    (tmp_path / "akira.json").write_text("not-json", encoding="utf-8")

    with pytest.raises(CharacterBibleStateError, match="could not be read"):
        await repository.load("akira")

    (tmp_path / "akira.json").write_text(
        json.dumps({"schema_version": 99, "character_bible": _bible().to_dict()}),
        encoding="utf-8",
    )
    with pytest.raises(CharacterBibleStateError, match="Unsupported"):
        await repository.load("akira")


@pytest.mark.asyncio
async def test_repository_rejects_character_id_path_traversal(tmp_path):
    repository = LocalJsonCharacterBibleRepository(tmp_path / "bibles")

    with pytest.raises(ValueError, match="portable identifier"):
        await repository.save(_bible("../akira"))

    assert not (tmp_path / "akira.json").exists()
