"""Model capability lock: identity, execution target, and allowed tasks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.domain.exceptions import PreProductionValidationError

_SHA256_OR_PENDING = re.compile(r"^(?:[0-9a-fA-F]{64}|PENDING|NOT_INSTALLED|NOT_APPLICABLE)$")
_FORBIDDEN_TASKS = frozenset({"approve_asset", "set_ready", "change_timeline", "choose_final_take"})


@dataclass(frozen=True)
class ModelCapability:
    model_id: str
    revision: str
    file_sha256: str
    license: str
    runtime: str
    quantization: str
    vram_limit_gb: float
    workflow_hash: str
    allowed_tasks: tuple[str, ...]
    execution_target: str
    forbidden_tasks: tuple[str, ...] = tuple(sorted(_FORBIDDEN_TASKS))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model_id.strip() or not self.revision.strip() or not self.license.strip():
            raise PreProductionValidationError("Model capability identity is incomplete.")
        if not _SHA256_OR_PENDING.fullmatch(self.file_sha256):
            raise PreProductionValidationError("Model capability file_sha256 is invalid.")
        if not self._valid_digest_or_pending(self.workflow_hash):
            raise PreProductionValidationError("Model capability workflow_hash is invalid.")
        if self.vram_limit_gb <= 0 or not self.allowed_tasks:
            raise PreProductionValidationError("Model capability requires VRAM and allowed tasks.")
        if set(self.allowed_tasks) & _FORBIDDEN_TASKS:
            raise PreProductionValidationError("Model capability cannot own approval, readiness, timeline, or take decisions.")
        if not set(_FORBIDDEN_TASKS).issubset(self.forbidden_tasks):
            raise PreProductionValidationError("Model capability must forbid production authority tasks.")
        if self.execution_target not in {"LOCAL", "RENTED_GPU"}:
            raise PreProductionValidationError("Unknown model execution target.")

    @staticmethod
    def _valid_digest_or_pending(value: str) -> bool:
        return bool(_SHA256_OR_PENDING.fullmatch(str(value)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "file_sha256": self.file_sha256,
            "license": self.license,
            "runtime": self.runtime,
            "quantization": self.quantization,
            "vram_limit_gb": self.vram_limit_gb,
            "workflow_hash": self.workflow_hash,
            "allowed_tasks": list(self.allowed_tasks),
            "execution_target": self.execution_target,
            "forbidden_tasks": list(self.forbidden_tasks),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModelCapability":
        return cls(
            model_id=str(data.get("model_id", "")),
            revision=str(data.get("revision", "")),
            file_sha256=str(data.get("file_sha256", "")),
            license=str(data.get("license", "")),
            runtime=str(data.get("runtime", "")),
            quantization=str(data.get("quantization", "")),
            vram_limit_gb=float(data.get("vram_limit_gb", 0)),
            workflow_hash=str(data.get("workflow_hash", "")),
            allowed_tasks=tuple(str(item) for item in data.get("allowed_tasks", ())),
            execution_target=str(data.get("execution_target", "")),
            forbidden_tasks=tuple(str(item) for item in data.get("forbidden_tasks", ())),
            metadata=(dict(data.get("metadata", {})) if isinstance(data.get("metadata", {}), Mapping) else {}),
        )
