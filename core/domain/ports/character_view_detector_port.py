from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.character_view_qc import CharacterViewObservation


class CharacterViewDetectorPort(ABC):
    """Detect people, faces, framing and orientation in one character view."""

    @abstractmethod
    async def inspect(
        self, *, image_bytes: bytes, expected_view: str
    ) -> CharacterViewObservation:
        raise NotImplementedError
