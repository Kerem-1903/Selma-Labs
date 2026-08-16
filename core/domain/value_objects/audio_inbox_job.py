"""Durable claim metadata for one licensed local audio item."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioInboxJob:
    """A claimed source file and the pipeline run that owns its processing."""

    job_id: str
    run_id: str
    source_uri: str
    attempts: int

    def __post_init__(self) -> None:
        if not self.job_id.strip() or not self.run_id.strip():
            raise ValueError("Audio inbox job and run identifiers must not be empty.")
        if not self.source_uri.strip():
            raise ValueError("Audio inbox source_uri must not be empty.")
        if self.attempts < 0:
            raise ValueError("Audio inbox attempts must not be negative.")
