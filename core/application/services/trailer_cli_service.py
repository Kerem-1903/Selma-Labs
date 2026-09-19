"""Application boundary for trailer CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.application.services.trailer_director_service import TrailerDirectorService
from core.domain.value_objects.episode_director_plan import EpisodeDirectorPlan
from core.domain.value_objects.trailer_brief import TrailerBrief


class TrailerCliService:
    def init(self, trailer_id: str) -> dict[str, Any]:
        return TrailerBrief(trailer_id=trailer_id).to_dict()

    def plan(self, episode_payload: dict[str, Any], brief_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        raw = episode_payload.get("episode_director_plan", episode_payload)
        if not isinstance(raw, dict):
            raise TypeError("Trailer input must contain an episode director plan object.")
        episode = EpisodeDirectorPlan.from_dict(raw)
        brief = TrailerBrief.from_dict(brief_payload or {}) if brief_payload else TrailerBrief(trailer_id="esik80-trailer-v1")
        return TrailerDirectorService().plan(episode, brief).to_dict()

    @staticmethod
    def load(path: str | Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"JSON file must contain an object: {path}")
        return payload
