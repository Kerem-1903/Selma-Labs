"""Atomic audit storage for human-approved episode scripts."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

from core.domain.entities.episode_script import EpisodeScript, EpisodeScriptStatus
from core.domain.exceptions import StoryApprovalError
from core.domain.ports.approval_repository_port import ApprovalRepositoryPort


class LocalJsonStoryApprovalRepository(ApprovalRepositoryPort):
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(self, directory: str | Path = ".selma_story_approvals") -> None:
        self._directory = Path(directory)

    async def record_story_approval(self, script: EpisodeScript) -> None:
        if script.status is not EpisodeScriptStatus.LOCKED or not script.approved_by:
            raise StoryApprovalError(
                "Only a human-approved locked script can be recorded."
            )
        if not self._SAFE_ID.fullmatch(script.id):
            raise StoryApprovalError("Episode script id is not storage-safe.")
        await asyncio.to_thread(self._write, script)

    def _write(self, script: EpisodeScript) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        target = self._directory / f"{script.id}.json"
        temporary = self._directory / f".{script.id}.{uuid.uuid4().hex}.tmp"
        payload = json.dumps(
            {"schema_version": 1, "episode_script": script.to_dict()},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
