from __future__ import annotations

import uuid

import pytest

from core.application.services.character_reference_asset_service import (
    CharacterReferenceAssetService,
)
from core.domain.entities.character_bible import CharacterBible
from core.domain.exceptions import StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.services.character_bible_validation_service import (
    CharacterBibleValidationService,
)
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.storage_reference import StorageReference
from core.domain.value_objects.style_profile import StyleProfile
from infrastructure.repositories.local_json_character_bible_repository import (
    LocalJsonCharacterBibleRepository,
)


class MemoryStorage(StoragePort):
    def __init__(self) -> None:
        self.assets: dict[str, bytes] = {}

    async def save(self, key: str, data: bytes, content_type: str) -> StorageReference:
        del content_type
        self.assets[key] = data
        return StorageReference(key=key, path=f"memory://{key}", size_bytes=len(data))

    async def load(self, key: str) -> bytes:
        try:
            return self.assets[key]
        except KeyError as error:
            raise StorageError(f"Missing memory asset: {key}") from error

    async def exists(self, key: str) -> bool:
        return key in self.assets

    def upload_file(self, file_stream, destination_path: str, content_type: str) -> str:
        del file_stream, content_type
        return f"memory://{destination_path}"

    def download_file(self, source_path: str, local_destination: str) -> bool:
        del source_path, local_destination
        return False

    def delete_file(self, file_path: str) -> bool:
        return self.assets.pop(file_path, None) is not None


def _bible() -> CharacterBible:
    return CharacterBible(
        character_id="akira",
        identity_constraints=IdentityConstraints("Brown", "Black", "Angular", "Athletic", "Tall"),
        style_profile=StyleProfile("Anime"),
    )


@pytest.mark.asyncio
async def test_akira_five_view_pack_round_trips_metadata_and_storage(tmp_path):
    storage = MemoryStorage()
    asset_service = CharacterReferenceAssetService(storage)
    repository = LocalJsonCharacterBibleRepository(tmp_path / "bibles")
    bible = _bible()
    expected: dict[ReferenceView, bytes] = {}

    for view in CharacterBibleValidationService.DEFAULT_REQUIRED_VIEWS:
        image = f"akira-{view.value}".encode()
        expected[view] = image
        reference = await asset_service.save_reference(
            bible,
            view,
            image,
            "image/png",
        )
        uuid.UUID(reference.id)
        uuid.UUID(reference.asset_id)
        assert reference.storage_key.startswith("characters/akira/references/")
        assert ":\\" not in reference.storage_key
        assert reference.revision == 1

    validation = CharacterBibleValidationService().validate(bible)
    assert validation.is_complete is True

    await repository.save(bible)
    persisted_json = (tmp_path / "bibles" / "akira.json").read_text(encoding="utf-8")
    assert "memory://" not in persisted_json
    assert ":\\\\" not in persisted_json
    restored = await repository.load("akira")

    for view, image in expected.items():
        reference = restored.reference_pack[view]
        assert await storage.exists(reference.storage_key)
        assert await asset_service.load_reference(reference) == image


@pytest.mark.asyncio
async def test_replacing_view_creates_new_asset_revision_without_overwrite():
    storage = MemoryStorage()
    service = CharacterReferenceAssetService(storage)
    bible = _bible()

    first = await service.save_reference(
        bible, ReferenceView.FRONT, b"first", "image/jpeg"
    )
    second = await service.save_reference(
        bible, ReferenceView.FRONT, b"second", "image/jpeg"
    )

    assert first.asset_id != second.asset_id
    assert first.storage_key != second.storage_key
    assert first.revision == 1
    assert second.revision == 2
    assert storage.assets[first.storage_key] == b"first"
    assert storage.assets[second.storage_key] == b"second"


@pytest.mark.asyncio
async def test_load_reference_detects_corrupted_storage_bytes():
    storage = MemoryStorage()
    service = CharacterReferenceAssetService(storage)
    reference = await service.save_reference(
        _bible(), ReferenceView.FRONT, b"expected", "image/webp"
    )
    storage.assets[reference.storage_key] = b"corrupted"

    with pytest.raises(StorageError, match="content-hash"):
        await service.load_reference(reference)
