"""Shared envelope for discovery and production artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.domain.exceptions import PreProductionValidationError


@dataclass(frozen=True)
class ArtifactEnvelope:
    """Common outer contract; payload schemas may evolve independently."""

    schema_version: int
    artifact_mode: str
    artifact_type: str
    production_eligible: bool
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise PreProductionValidationError("Artifact envelope schema_version must be 1.")
        if self.artifact_mode not in {"DISCOVERY", "PRODUCTION"}:
            raise PreProductionValidationError("Artifact mode must be DISCOVERY or PRODUCTION.")
        if not self.artifact_type.strip():
            raise PreProductionValidationError("Artifact type must not be empty.")
        if self.artifact_mode == "DISCOVERY" and self.production_eligible:
            raise PreProductionValidationError("Discovery artifacts cannot be production eligible.")
        if not isinstance(self.payload, Mapping):
            raise PreProductionValidationError("Artifact payload must be an object.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_mode": self.artifact_mode,
            "artifact_type": self.artifact_type,
            "production_eligible": self.production_eligible,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ArtifactEnvelope:
        payload = data.get("payload", {})
        return cls(
            schema_version=int(data.get("schema_version", 0)),
            artifact_mode=str(data.get("artifact_mode", "")),
            artifact_type=str(data.get("artifact_type", "")),
            production_eligible=bool(data.get("production_eligible", False)),
            payload=payload if isinstance(payload, Mapping) else {},
        )
