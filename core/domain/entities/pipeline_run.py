"""Durable aggregate root for one autonomous Shorts Factory execution."""
from __future__ import annotations

import uuid
import hmac
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from core.domain.exceptions import PipelineRunStateError


class PipelineRunStatus(str, Enum):
    """Lifecycle states that may be persisted for a pipeline execution."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


@dataclass(init=False)
class PipelineRun:
    """Aggregate root that records durable stage checkpoints and failures.

    Stage artifacts are internal aggregate state. Callers receive a deep,
    read-only snapshot through :attr:`artifact_manifest`; mutations must pass
    through :meth:`mark_stage_completed` so lifecycle invariants stay intact.
    """

    run_id: str
    status: PipelineRunStatus
    current_stage: str
    retry_count: int
    failure_reason: str | None
    max_retries: int
    input_fingerprint: str | None
    created_at: datetime
    updated_at: datetime
    _artifact_manifest: dict[str, dict[str, Any]] = field(repr=False)

    def __init__(
        self,
        run_id: str,
        status: PipelineRunStatus = PipelineRunStatus.PENDING,
        current_stage: str = "PENDING",
        retry_count: int = 0,
        artifact_manifest: Mapping[str, Mapping[str, Any]] | None = None,
        failure_reason: str | None = None,
        max_retries: int = 3,
        input_fingerprint: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        """Create or rehydrate an aggregate without exposing mutable state."""
        now = datetime.now(timezone.utc)
        self.run_id = run_id
        self.status = status
        self.current_stage = current_stage
        self.retry_count = retry_count
        self.failure_reason = failure_reason
        self.max_retries = max_retries
        self.input_fingerprint = input_fingerprint
        self.created_at = created_at or now
        self.updated_at = updated_at or now
        self._artifact_manifest = deepcopy(dict(artifact_manifest or {}))
        self.__post_init__()

    def __post_init__(self) -> None:
        """Validate persisted state before it can participate in transitions."""
        try:
            uuid.UUID(self.run_id)
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError("PipelineRun run_id must be a valid UUID.") from error
        if not isinstance(self.status, PipelineRunStatus):
            self.status = PipelineRunStatus(self.status)
        if not self.current_stage.strip():
            raise ValueError("PipelineRun current_stage must not be empty.")
        if self.retry_count < 0:
            raise ValueError("PipelineRun retry_count must not be negative.")
        if self.max_retries < 0:
            raise ValueError("PipelineRun max_retries must not be negative.")
        if self.input_fingerprint is not None:
            normalized_fingerprint = self.input_fingerprint.strip().lower()
            if len(normalized_fingerprint) != 64 or any(
                character not in "0123456789abcdef"
                for character in normalized_fingerprint
            ):
                raise ValueError(
                    "PipelineRun input_fingerprint must be a SHA-256 hex digest."
                )
            self.input_fingerprint = normalized_fingerprint
        if any(not stage.strip() for stage in self._artifact_manifest):
            raise ValueError("PipelineRun artifact stages must not be empty.")
        if any(not isinstance(data, dict) for data in self._artifact_manifest.values()):
            raise ValueError("PipelineRun artifacts must be dictionaries.")

    @property
    def artifact_manifest(self) -> Mapping[str, Mapping[str, Any]]:
        """Return a deep, immutable manifest snapshot for inspection only."""
        def _freeze(obj):
            if isinstance(obj, dict):
                return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
            elif isinstance(obj, list):
                return tuple(_freeze(v) for v in obj)
            return obj

        return _freeze(self._artifact_manifest)

    @classmethod
    def create(cls, *, max_retries: int = 3) -> "PipelineRun":
        """Start a new pending execution with a unique, durable identity."""
        return cls(run_id=str(uuid.uuid4()), max_retries=max_retries)

    def has_completed_stage(self, stage_name: str) -> bool:
        """Return whether a stage has a persisted success artifact."""
        return stage_name in self._artifact_manifest

    def get_stage_artifact(self, stage_name: str) -> dict[str, Any]:
        """Return an isolated copy of one persisted success artifact."""
        return deepcopy(self._artifact_manifest[stage_name])

    def bind_input_fingerprint(self, fingerprint: str) -> None:
        """Bind this run to one immutable source/options identity.

        Legacy runs that already contain artifacts cannot be bound safely: the
        original CLI inputs were not persisted, so accepting the current input
        could silently combine old paid-stage artifacts with a new request.
        """
        normalized = fingerprint.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("input fingerprint must be a SHA-256 hex digest.")
        if self.input_fingerprint is None:
            if self._artifact_manifest:
                raise PipelineRunStateError(
                    "This legacy pipeline run has checkpoints but no input fingerprint; "
                    "start a new run to avoid mixing artifacts from different inputs."
                )
            self.input_fingerprint = normalized
            self._touch()
            return
        if not hmac.compare_digest(self.input_fingerprint, normalized):
            raise PipelineRunStateError(
                "The requested topic/audio or pipeline options do not match this run."
            )

    def rebind_input_fingerprint_after_reprocess(self, fingerprint: str) -> None:
        """Accept a new config identity only after explicit stage invalidation."""
        if self.status is not PipelineRunStatus.FAILED or not (
            self.failure_reason or ""
        ).startswith("Explicit reprocessing requested"):
            raise PipelineRunStateError(
                "A fingerprint can be rebound only during explicit stage reprocessing."
            )
        normalized = fingerprint.strip().lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("input fingerprint must be a SHA-256 hex digest.")
        self.input_fingerprint = normalized
        self._touch()

    def begin_stage(self, stage_name: str) -> None:
        """Transition the run into a stage before an external operation starts."""
        self._require_stage_name(stage_name)
        if self.status is PipelineRunStatus.COMPLETED:
            raise PipelineRunStateError("A completed pipeline run cannot start a stage.")
        if self.status is PipelineRunStatus.FAILED:
            if not self.can_retry():
                raise PipelineRunStateError("Pipeline run has exhausted its retry budget.")
            self.retry_count += 1

        self.status = PipelineRunStatus.RUNNING
        self.current_stage = stage_name
        self.failure_reason = None
        self._touch()

    def add_artifact(self, stage_name: str, artifact_data: Mapping[str, Any]) -> None:
        """Add a checkpoint only for the currently running stage.

        This is the sole mutation boundary for the manifest. It prevents an
        outside caller from inserting an artifact for an inactive stage.
        """
        self._require_stage_name(stage_name)
        if self.status is not PipelineRunStatus.RUNNING:
            raise PipelineRunStateError("Only a running pipeline run can add an artifact.")
        if self.current_stage != stage_name:
            raise PipelineRunStateError(
                f"Cannot add '{stage_name}' while '{self.current_stage}' is active."
            )
        if not isinstance(artifact_data, Mapping):
            raise ValueError("Pipeline stage artifact_data must be a mapping.")
        self._artifact_manifest[stage_name] = deepcopy(dict(artifact_data))
        self._touch()

    def mark_stage_completed(
        self,
        stage_name: str,
        artifact_data: dict[str, Any],
    ) -> None:
        """Durably register a successful stage result in the manifest."""
        self.add_artifact(stage_name, artifact_data)

    def mark_failed(self, reason: str) -> None:
        """Record a failure while preserving all previously saved artifacts."""
        if self.status is PipelineRunStatus.COMPLETED:
            raise PipelineRunStateError("A completed pipeline run cannot be marked failed.")
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("Pipeline failure reason must not be empty.")

        self.status = PipelineRunStatus.FAILED
        self.failure_reason = normalized_reason
        self._touch()

    def can_retry(self) -> bool:
        """Return whether a failed run still has a recovery attempt available."""
        return (
            self.status is PipelineRunStatus.FAILED
            and self.retry_count < self.max_retries
        )

    def extend_retry_budget(self, additional_attempts: int) -> None:
        """Explicitly authorize recovery attempts for an exhausted failed run."""
        if additional_attempts <= 0:
            raise ValueError("additional_attempts must be greater than zero.")
        if self.status is not PipelineRunStatus.FAILED:
            raise PipelineRunStateError(
                "Retry budget can be extended only for a failed pipeline run."
            )
        self.max_retries += additional_attempts
        self._touch()

    def reopen_with_invalidated_stages(self, stage_names: list[str]) -> None:
        """Reopen a terminal run while preserving every upstream checkpoint."""
        if self.status not in {PipelineRunStatus.COMPLETED, PipelineRunStatus.FAILED}:
            raise PipelineRunStateError(
                "Only a completed or failed pipeline run can be reprocessed."
            )
        normalized = [stage.strip() for stage in stage_names if stage.strip()]
        if not normalized:
            raise ValueError("At least one stage must be invalidated.")
        for stage_name in normalized:
            self._artifact_manifest.pop(stage_name, None)
        self.status = PipelineRunStatus.FAILED
        self.current_stage = normalized[0]
        self.failure_reason = (
            f"Explicit reprocessing requested from stage '{normalized[0]}'."
        )
        self._touch()

    def mark_completed(self) -> None:
        """Mark the complete multi-stage workflow successful after its final stage."""
        if self.status is not PipelineRunStatus.RUNNING:
            raise PipelineRunStateError("Only a running pipeline run can be completed.")
        self.status = PipelineRunStatus.COMPLETED
        self._touch()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the aggregate for a JSON- or database-backed adapter."""
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "current_stage": self.current_stage,
            "retry_count": self.retry_count,
            "artifact_manifest": deepcopy(self._artifact_manifest),
            "failure_reason": self.failure_reason,
            "max_retries": self.max_retries,
            "input_fingerprint": self.input_fingerprint,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineRun":
        """Rehydrate a run previously exported by :meth:`to_dict`."""
        return cls(
            run_id=str(data["run_id"]),
            status=PipelineRunStatus(data["status"]),
            current_stage=str(data["current_stage"]),
            retry_count=int(data["retry_count"]),
            artifact_manifest=deepcopy(data.get("artifact_manifest", {})),
            failure_reason=data.get("failure_reason"),
            max_retries=int(data.get("max_retries", 3)),
            input_fingerprint=data.get("input_fingerprint"),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )

    @staticmethod
    def _require_stage_name(stage_name: str) -> None:
        if not stage_name or not stage_name.strip():
            raise ValueError("Pipeline stage_name must not be empty.")

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
