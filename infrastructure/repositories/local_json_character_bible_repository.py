"""Local JSON adapter for durable character-bible metadata."""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from core.domain.entities.character_bible import CharacterBible
from core.domain.exceptions import CharacterBibleNotFoundError, CharacterBibleStateError
from core.domain.ports.character_bible_repository_port import CharacterBibleRepositoryPort


class LocalJsonCharacterBibleRepository(CharacterBibleRepositoryPort):
    SCHEMA_VERSION = 1
    _SAFE_CHARACTER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(self, base_directory: str | Path = ".selma_character_bibles") -> None:
        self._base_directory = Path(base_directory)

    async def save(self, bible: CharacterBible) -> None:
        self._validate_character_id(bible.character_id)
        envelope = {
            "schema_version": self.SCHEMA_VERSION,
            "character_bible": bible.to_dict(),
        }
        await asyncio.to_thread(self._write_envelope, bible.character_id, envelope)

    async def load(self, character_id: str) -> CharacterBible:
        self._validate_character_id(character_id)
        try:
            envelope = await asyncio.to_thread(self._read_envelope, character_id)
        except FileNotFoundError as error:
            raise CharacterBibleNotFoundError(
                f"Character bible '{character_id}' was not found."
            ) from error
        except (json.JSONDecodeError, OSError, UnicodeError, ValueError) as error:
            raise CharacterBibleStateError(
                f"Persisted character bible '{character_id}' could not be read."
            ) from error

        if envelope.get("schema_version") != self.SCHEMA_VERSION:
            raise CharacterBibleStateError(
                f"Unsupported character-bible schema version for '{character_id}'."
            )
        try:
            bible = CharacterBible.from_dict(envelope["character_bible"])
        except (KeyError, TypeError, ValueError) as error:
            raise CharacterBibleStateError(
                f"Persisted character bible '{character_id}' is invalid."
            ) from error
        if bible.character_id != character_id:
            raise CharacterBibleStateError(
                f"Persisted character ID does not match requested '{character_id}'."
            )
        return bible

    def _write_envelope(self, character_id: str, envelope: dict[str, Any]) -> None:
        self._base_directory.mkdir(parents=True, exist_ok=True)
        target_path = self._path_for(character_id)
        temporary_path = self._base_directory / (
            f".{character_id}.{uuid.uuid4().hex}.tmp"
        )
        serialized = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True)
        try:
            with temporary_path.open("w", encoding="utf-8") as temporary_file:
                temporary_file.write(serialized)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, target_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _read_envelope(self, character_id: str) -> dict[str, Any]:
        parsed = json.loads(self._path_for(character_id).read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Character-bible JSON must contain an object.")
        return parsed

    def _path_for(self, character_id: str) -> Path:
        return self._base_directory / f"{character_id}.json"

    @classmethod
    def _validate_character_id(cls, character_id: str) -> None:
        if not isinstance(character_id, str) or not cls._SAFE_CHARACTER_ID.fullmatch(character_id):
            raise ValueError(
                "character_id must be a portable identifier containing only letters, "
                "numbers, dots, underscores, or hyphens."
            )
