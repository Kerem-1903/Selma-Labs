from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

from core.domain.entities.shot_motion_clip import ShotMotionClip
from core.domain.exceptions import ShotMotionClipStateError
from core.domain.ports.shot_motion_clip_repository_port import (
    ShotMotionClipRepositoryPort,
)


class LocalJsonShotMotionClipRepository(ShotMotionClipRepositoryPort):
    SCHEMA_VERSION = 1
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(self, base_directory: str | Path = ".selma_motion_clips") -> None:
        self._base_directory = Path(base_directory)

    async def save(self, clip: ShotMotionClip) -> None:
        self._validate_id(clip.id)
        await asyncio.to_thread(
            self._write,
            clip.id,
            {"schema_version": self.SCHEMA_VERSION, "shot_motion_clip": clip.to_dict()},
        )

    async def load(self, clip_id: str) -> ShotMotionClip:
        self._validate_id(clip_id)
        try:
            envelope = await asyncio.to_thread(self._read, clip_id)
            if envelope.get("schema_version") != self.SCHEMA_VERSION:
                raise ValueError("Unsupported schema version.")
            clip = ShotMotionClip.from_dict(envelope["shot_motion_clip"])
            if clip.id != clip_id:
                raise ValueError("Motion clip ID does not match its file name.")
            return clip
        except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError, TypeError, ValueError) as error:
            raise ShotMotionClipStateError(
                f"Shot motion clip '{clip_id}' could not be read."
            ) from error

    def _write(self, clip_id: str, envelope: dict) -> None:
        self._base_directory.mkdir(parents=True, exist_ok=True)
        target = self._path_for(clip_id)
        temporary = self._base_directory / f".{clip_id}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(envelope, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _read(self, clip_id: str) -> dict:
        parsed = json.loads(self._path_for(clip_id).read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Motion clip JSON must contain an object.")
        return parsed

    def _path_for(self, clip_id: str) -> Path:
        return self._base_directory / f"{clip_id}.json"

    @classmethod
    def _validate_id(cls, clip_id: str) -> None:
        if not isinstance(clip_id, str) or not cls._SAFE_ID.fullmatch(clip_id):
            raise ValueError("clip_id must be a portable identifier.")
