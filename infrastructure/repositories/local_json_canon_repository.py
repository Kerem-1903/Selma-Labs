"""Read the active locked pre-production canon from versioned JSON assets."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.direction_bible import (
    CreativeDirectionBible,
    VisualStyleBible,
    WorldBible,
)
from core.domain.exceptions import PreProductionStateError
from core.domain.ports.canon_repository_port import CanonRepositoryPort


class LocalJsonCanonRepository(CanonRepositoryPort):
    SCHEMA_VERSION = 1

    def __init__(
        self, canon_directory: str | Path, character_directory: str | Path
    ) -> None:
        self._canon_directory = Path(canon_directory)
        self._character_directory = Path(character_directory)

    async def get_creative_direction(self) -> CreativeDirectionBible:
        payload = await self._read("creative-direction.json", "creative_direction")
        return CreativeDirectionBible.from_dict(payload)

    async def get_world_bible(self) -> WorldBible:
        payload = await self._read("world-bible.json", "world_bible")
        return WorldBible.from_dict(payload)

    async def get_visual_style(self) -> VisualStyleBible:
        payload = await self._read("visual-style.json", "visual_style")
        return VisualStyleBible.from_dict(payload)

    async def get_character_bibles(self) -> tuple[CharacterBible, ...]:
        paths = await asyncio.to_thread(
            lambda: sorted(self._character_directory.glob("*.json"))
        )
        if not paths:
            raise PreProductionStateError("No CharacterBible assets were found.")
        bibles = []
        for path in paths:
            envelope = await self._read_path(path)
            try:
                bibles.append(
                    CharacterBible.from_dict(dict(envelope["character_bible"]))
                )
            except (KeyError, TypeError, ValueError) as error:
                raise PreProductionStateError(
                    f"CharacterBible asset '{path.name}' is invalid."
                ) from error
        return tuple(bibles)

    async def _read(self, filename: str, key: str) -> dict[str, Any]:
        envelope = await self._read_path(self._canon_directory / filename)
        try:
            return dict(envelope[key])
        except (KeyError, TypeError, ValueError) as error:
            raise PreProductionStateError(
                f"Canon asset '{filename}' is invalid."
            ) from error

    async def _read_path(self, path: Path) -> dict[str, Any]:
        try:
            envelope = await asyncio.to_thread(
                lambda: json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PreProductionStateError(
                f"Canon asset '{path.name}' could not be read."
            ) from error
        if (
            not isinstance(envelope, dict)
            or envelope.get("schema_version") != self.SCHEMA_VERSION
        ):
            raise PreProductionStateError(
                f"Canon asset '{path.name}' has an unsupported schema."
            )
        return envelope
