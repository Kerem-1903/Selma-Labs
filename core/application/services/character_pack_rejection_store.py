"""Storage helpers for character pack rejection receipts.

Both pack types (view pack and pose pack) record and read refusals the same
way, so the load/record rules -- including "a refusal cannot be rewritten" --
live here instead of drifting apart in two services.
"""

from __future__ import annotations

import json

from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_pack_rejection import CharacterPackRejection


async def load_rejection(
    storage: StoragePort, key: str
) -> CharacterPackRejection | None:
    """Return the rejection recorded at ``key``, or ``None`` when there is none."""
    if not await storage.exists(key):
        return None
    raw = json.loads((await storage.load(key)).decode("utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("Character pack rejection receipt must contain an object.")
    return CharacterPackRejection.from_dict(raw)


async def record_rejection(
    storage: StoragePort, key: str, rejection: CharacterPackRejection
) -> CharacterPackRejection:
    """Persist ``rejection``, or return the identical receipt already on disk.

    Recording the same refusal twice is idempotent. Recording a *different*
    refusal for the same pack is refused: a receipt an operator could edit to
    reopen a rejected pack would not be a verdict.
    """
    existing = await load_rejection(storage, key)
    if existing is not None:
        if (
            existing.reason != rejection.reason
            or existing.rejected_by != rejection.rejected_by
            or dict(existing.rejected_hashes) != dict(rejection.rejected_hashes)
            or existing.superseded_by_version != rejection.superseded_by_version
        ):
            raise ValueError(
                "This character version carries a different recorded rejection; "
                "a refusal cannot be rewritten."
            )
        return existing
    payload = (json.dumps(rejection.to_dict(), indent=2, sort_keys=True) + "\n").encode()
    await storage.save(key, payload, "application/json")
    return rejection
