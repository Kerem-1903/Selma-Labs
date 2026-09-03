from __future__ import annotations

import re
from typing import Any

from core.domain.entities.location_bible import LocationBible


class LocationBibleFactoryService:
    """Convert a concise creative brief into a strict reusable location contract."""

    @staticmethod
    def create(brief: dict[str, Any]) -> LocationBible:
        payload = dict(brief)
        if not payload.get("location_id") and payload.get("name"):
            payload["location_id"] = re.sub(
                r"[^a-z0-9]+", "-", str(payload["name"]).casefold()
            ).strip("-")
        payload.setdefault("weather_options", ["clear"])
        payload.setdefault("interaction_points", [])
        payload.setdefault("architecture", [])
        payload.setdefault("forbidden_elements", [])
        payload["locked"] = False
        return LocationBible.from_dict(payload)
