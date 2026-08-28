import pytest
import os
from pathlib import Path
from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.character_reference import CharacterReference
from core.domain.value_objects.style_profile import StyleProfile
from infrastructure.repositories.local_json_character_bible_repository import (
    LocalJsonCharacterBibleRepository,
    CharacterBibleNotFoundError
)

@pytest.fixture
def repo(tmp_path):
    return LocalJsonCharacterBibleRepository(base_directory=tmp_path)

@pytest.fixture
def sample_bible():
    constraints = IdentityConstraints(
        eye_color="Brown",
        hair="Black spiky",
        facial_geometry="Angular",
        body_proportions="Athletic",
        silhouette="Tall",
        immutable_marks=["Scar"]
    )
    profile = StyleProfile("Anime")
    ref = CharacterReference("ref_1", "akira", ReferenceView.FRONT, "asset_abc", revision=2, content_hash="hash123")

    return CharacterBible(
        character_id="akira",
        identity_constraints=constraints,
        style_profile=profile,
        reference_pack={ReferenceView.FRONT: ref},
        schema_version=2
    )

@pytest.mark.asyncio
async def test_save_and_load_bible(repo, sample_bible):
    await repo.save(sample_bible)

    loaded_bible = await repo.load("akira")

    assert loaded_bible.character_id == "akira"
    assert loaded_bible.schema_version == 2
    assert loaded_bible.identity_constraints.hair == "Black spiky"
    assert ReferenceView.FRONT in loaded_bible.reference_pack

    ref = loaded_bible.reference_pack[ReferenceView.FRONT]
    assert ref.asset_id == "asset_abc"
    assert ref.revision == 2
    assert ref.content_hash == "hash123"

@pytest.mark.asyncio
async def test_missing_file_raises_error(repo):
    with pytest.raises(CharacterBibleNotFoundError):
        await repo.load("non_existent_character")
