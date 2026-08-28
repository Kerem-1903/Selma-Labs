import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from core.domain.entities.character_bible import CharacterBible
from core.domain.ports.character_bible_repository_port import CharacterBibleRepositoryPort

class CharacterBibleNotFoundError(Exception):
    pass

class CharacterBibleStateError(Exception):
    pass

class LocalJsonCharacterBibleRepository(CharacterBibleRepositoryPort):
    """Persist `CharacterBible` aggregates as atomically replaced JSON files."""

    def __init__(
        self,
        base_directory: str | Path = ".selma_character_bibles",
        *,
        lock_timeout_seconds: float = 300.0,
    ) -> None:
        if lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be greater than zero.")
        self._base_directory = Path(base_directory)
        self._lock_timeout_seconds = lock_timeout_seconds
        self._held_char_ids: ContextVar[frozenset[str]] = ContextVar(
            "local_json_character_bible_repository_held_ids",
            default=frozenset(),
        )

    async def save(self, bible: CharacterBible) -> None:
        async with self.lock_character(bible.character_id):
            await asyncio.to_thread(self._write_bible, bible.to_dict())

    async def load(self, character_id: str) -> CharacterBible:
        if not character_id:
            raise ValueError("character_id must be provided.")

        try:
            data = await asyncio.to_thread(self._read_bible, character_id)
        except FileNotFoundError as error:
            raise CharacterBibleNotFoundError(f"CharacterBible '{character_id}' not found.") from error
        except (json.JSONDecodeError, OSError, UnicodeError) as error:
            raise CharacterBibleStateError(f"Persisted CharacterBible '{character_id}' could not be read.") from error

        try:
            bible = CharacterBible.from_dict(data)
        except (KeyError, TypeError, ValueError) as error:
            raise CharacterBibleStateError(f"Persisted CharacterBible '{character_id}' is invalid.") from error

        return bible

    @asynccontextmanager
    async def lock_character(self, character_id: str) -> AsyncIterator[None]:
        if not character_id:
            raise ValueError("character_id must be provided.")

        held_ids = self._held_char_ids.get()
        if character_id in held_ids:
            yield
            return

        self._base_directory.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(self._lock_path_for(character_id)), thread_local=False)
        try:
            await asyncio.to_thread(lock.acquire, timeout=self._lock_timeout_seconds)
        except Timeout as error:
            raise CharacterBibleStateError(
                f"Timed out waiting for the lock on CharacterBible '{character_id}'."
            ) from error

        token = self._held_char_ids.set(held_ids | {character_id})
        try:
            yield
        finally:
            self._held_char_ids.reset(token)
            await asyncio.to_thread(lock.release)

    def _write_bible(self, data: dict[str, Any]) -> None:
        char_id = str(data["character_id"])
        if not char_id:
            raise ValueError("character_id must be provided in data.")

        self._base_directory.mkdir(parents=True, exist_ok=True)
        target_path = self._path_for(char_id)
        temporary_path = self._base_directory / f".{char_id}.{uuid.uuid4().hex}.tmp"

        serialized = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        with temporary_path.open("w", encoding="utf-8") as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, target_path)

    def _read_bible(self, character_id: str) -> dict[str, Any]:
        raw = self._path_for(character_id).read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("CharacterBible JSON must contain an object.")
        return parsed

    def _path_for(self, character_id: str) -> Path:
        return self._base_directory / f"{character_id}.json"

    def _lock_path_for(self, character_id: str) -> Path:
        return self._base_directory / f"{character_id}.lock"
