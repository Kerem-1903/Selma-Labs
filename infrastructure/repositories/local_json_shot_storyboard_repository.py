from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import ShotStoryboardNotFoundError, ShotStoryboardStateError
from core.domain.ports.shot_storyboard_repository_port import ShotStoryboardRepositoryPort


class LocalJsonShotStoryboardRepository(ShotStoryboardRepositoryPort):
    SCHEMA_VERSION = 1
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(self, base_directory: str | Path = ".selma_storyboards") -> None:
        self._base_directory = Path(base_directory)

    async def save(self, storyboard: ShotStoryboard) -> None:
        self._validate_id(storyboard.id)
        envelope = {
            "schema_version": self.SCHEMA_VERSION,
            "shot_storyboard": storyboard.to_dict(),
        }
        await asyncio.to_thread(self._write_envelope, storyboard.id, envelope)

    async def load(self, storyboard_id: str) -> ShotStoryboard:
        self._validate_id(storyboard_id)
        try:
            envelope = await asyncio.to_thread(self._read_envelope, storyboard_id)
        except FileNotFoundError as error:
            raise ShotStoryboardNotFoundError(
                f"Shot storyboard '{storyboard_id}' was not found."
            ) from error
        except (json.JSONDecodeError, OSError, UnicodeError, ValueError) as error:
            raise ShotStoryboardStateError(
                f"Persisted shot storyboard '{storyboard_id}' could not be read."
            ) from error

        if envelope.get("schema_version") != self.SCHEMA_VERSION:
            raise ShotStoryboardStateError(
                f"Unsupported shot-storyboard schema version for '{storyboard_id}'."
            )
        try:
            storyboard = ShotStoryboard.from_dict(envelope["shot_storyboard"])
        except (KeyError, TypeError, ValueError) as error:
            raise ShotStoryboardStateError(
                f"Persisted shot storyboard '{storyboard_id}' is invalid."
            ) from error
        if storyboard.id != storyboard_id:
            raise ShotStoryboardStateError(
                f"Persisted storyboard ID does not match requested '{storyboard_id}'."
            )
        return storyboard

    def _write_envelope(self, storyboard_id: str, envelope: dict[str, Any]) -> None:
        self._base_directory.mkdir(parents=True, exist_ok=True)
        target = self._path_for(storyboard_id)
        temporary = self._base_directory / f".{storyboard_id}.{uuid.uuid4().hex}.tmp"
        serialized = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _read_envelope(self, storyboard_id: str) -> dict[str, Any]:
        parsed = json.loads(self._path_for(storyboard_id).read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Shot-storyboard JSON must contain an object.")
        return parsed

    def _path_for(self, storyboard_id: str) -> Path:
        return self._base_directory / f"{storyboard_id}.json"

    @classmethod
    def _validate_id(cls, storyboard_id: str) -> None:
        if not isinstance(storyboard_id, str) or not cls._SAFE_ID.fullmatch(storyboard_id):
            raise ValueError("storyboard_id must be a portable identifier.")
