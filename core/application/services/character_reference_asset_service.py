from __future__ import annotations

import hashlib
import re
import uuid

from core.domain.entities.character_bible import CharacterBible
from core.domain.exceptions import StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_identity import ReferenceView
from core.domain.value_objects.character_reference import CharacterReference


class CharacterReferenceAssetService:
    """Store and retrieve character-reference bytes through ``StoragePort``."""

    _EXTENSIONS = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    _SAFE_CHARACTER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(self, storage: StoragePort) -> None:
        self._storage = storage

    async def save_reference(
        self,
        bible: CharacterBible,
        view: ReferenceView,
        data: bytes,
        content_type: str,
    ) -> CharacterReference:
        if not data:
            raise ValueError("Character reference data must not be empty.")
        if content_type not in self._EXTENSIONS:
            raise ValueError(f"Unsupported character reference content type: {content_type}")
        if not self._SAFE_CHARACTER_ID.fullmatch(bible.character_id):
            raise ValueError("Character ID is not safe for a portable storage key.")

        previous = bible.reference_pack.get(view)
        revision = previous.revision + 1 if previous else 1
        asset_id = str(uuid.uuid4())
        reference_id = str(uuid.uuid4())
        extension = self._EXTENSIONS[content_type]
        storage_key = (
            f"characters/{bible.character_id}/references/{view.value.lower()}/"
            f"{revision:04d}-{asset_id}{extension}"
        )
        content_hash = hashlib.sha256(data).hexdigest()

        stored = await self._storage.save(storage_key, data, content_type)
        if stored.key != storage_key:
            raise StorageError("Storage adapter returned a different key for the reference asset.")

        reference = CharacterReference(
            id=reference_id,
            character_id=bible.character_id,
            view=view,
            asset_id=asset_id,
            storage_key=storage_key,
            content_type=content_type,
            content_hash=content_hash,
            revision=revision,
        )
        bible.reference_pack[view] = reference
        return reference

    async def load_reference(self, reference: CharacterReference) -> bytes:
        if not reference.storage_key:
            raise StorageError("Character reference does not contain a storage key.")
        data = await self._storage.load(reference.storage_key)
        if reference.content_hash:
            actual_hash = hashlib.sha256(data).hexdigest()
            if actual_hash != reference.content_hash:
                raise StorageError(
                    f"Character reference '{reference.id}' failed content-hash verification."
                )
        return data
