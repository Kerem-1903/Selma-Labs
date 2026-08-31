from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

from core.domain.ports.shot_production_attempt_repository_port import (
    ShotProductionAttemptRepositoryPort,
)
from core.domain.value_objects.shot_production_attempt import ShotProductionAttempt


class LocalJsonShotProductionAttemptRepository(ShotProductionAttemptRepositoryPort):
    SCHEMA_VERSION = 1
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(self, base_directory: str | Path = ".selma_production_attempts") -> None:
        self._base_directory = Path(base_directory)
        self._lock = asyncio.Lock()

    async def save(self, attempt: ShotProductionAttempt) -> None:
        self._validate_id(attempt.shot_contract_id)
        async with self._lock:
            existing = await self.list_for_shot(attempt.shot_contract_id)
            if any(item.attempt_number == attempt.attempt_number for item in existing):
                raise ValueError("Production attempt number already exists for this shot.")
            await asyncio.to_thread(
                self._write,
                attempt.shot_contract_id,
                [*existing, attempt],
            )

    async def list_for_shot(self, shot_contract_id: str) -> list[ShotProductionAttempt]:
        self._validate_id(shot_contract_id)
        try:
            payload = await asyncio.to_thread(self._read, shot_contract_id)
        except FileNotFoundError:
            return []
        if payload.get("schema_version") != self.SCHEMA_VERSION:
            raise ValueError("Unsupported production-attempt schema version.")
        return [
            ShotProductionAttempt.from_dict(item)
            for item in payload.get("attempts", [])
        ]

    def _write(self, shot_contract_id: str, attempts: list[ShotProductionAttempt]) -> None:
        self._base_directory.mkdir(parents=True, exist_ok=True)
        target = self._path_for(shot_contract_id)
        temporary = self._base_directory / f".{shot_contract_id}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema_version": self.SCHEMA_VERSION,
                        "attempts": [item.to_dict() for item in attempts],
                    },
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _read(self, shot_contract_id: str) -> dict:
        value = json.loads(self._path_for(shot_contract_id).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Production-attempt JSON must contain an object.")
        return value

    def _path_for(self, shot_contract_id: str) -> Path:
        return self._base_directory / f"{shot_contract_id}.json"

    @classmethod
    def _validate_id(cls, shot_contract_id: str) -> None:
        if not isinstance(shot_contract_id, str) or not cls._SAFE_ID.fullmatch(shot_contract_id):
            raise ValueError("shot_contract_id must be a portable identifier.")
