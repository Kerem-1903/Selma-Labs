"""Canonical, provider-neutral definition of a reusable anime location."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class LocationBible:
    location_id: str
    name: str
    description: str
    immutable_geometry: tuple[str, ...]
    architecture: tuple[str, ...]
    palette: tuple[str, ...]
    lighting_sources: tuple[str, ...]
    interaction_points: tuple[str, ...]
    weather_options: tuple[str, ...]
    forbidden_elements: tuple[str, ...]
    style: str
    locked: bool = False

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.location_id):
            raise ValueError("Location ID must be portable and non-empty.")
        required = (self.name, self.description, self.style)
        if any(not value.strip() for value in required):
            raise ValueError("Location name, description and style are required.")
        if not self.immutable_geometry or not self.palette or not self.lighting_sources:
            raise ValueError("Location geometry, palette and lighting are required.")

    def prompt_fragments(self) -> tuple[str, ...]:
        return (
            self.description,
            *self.immutable_geometry,
            *self.architecture,
            f"color palette: {', '.join(self.palette)}",
            f"visible light sources: {', '.join(self.lighting_sources)}",
            self.style,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "location_id": self.location_id,
            "name": self.name,
            "description": self.description,
            "immutable_geometry": list(self.immutable_geometry),
            "architecture": list(self.architecture),
            "palette": list(self.palette),
            "lighting_sources": list(self.lighting_sources),
            "interaction_points": list(self.interaction_points),
            "weather_options": list(self.weather_options),
            "forbidden_elements": list(self.forbidden_elements),
            "style": self.style,
            "locked": self.locked,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LocationBible:
        def strings(name: str) -> tuple[str, ...]:
            raw = data.get(name, [])
            if not isinstance(raw, list):
                raise TypeError(f"Location field '{name}' must be a list.")
            return tuple(str(item).strip() for item in raw if str(item).strip())

        return cls(
            location_id=str(data["location_id"]),
            name=str(data["name"]),
            description=str(data["description"]),
            immutable_geometry=strings("immutable_geometry"),
            architecture=strings("architecture"),
            palette=strings("palette"),
            lighting_sources=strings("lighting_sources"),
            interaction_points=strings("interaction_points"),
            weather_options=strings("weather_options") or ("clear",),
            forbidden_elements=strings("forbidden_elements"),
            style=str(data["style"]),
            locked=bool(data.get("locked", False)),
        )
