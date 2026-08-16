"""One immutable word-level timestamp produced by an alignment provider."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WordTiming:
    """A spoken or sung word with millisecond-precise timing.

    Timing is expressed in the original audio asset's timeline, not relative
    to a selected highlight. This lets one alignment result serve multiple
    candidate highlights without introducing ambiguous offsets.
    """

    text: str
    start_ms: int
    end_ms: int
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("WordTiming text must not be empty.")
        if self.start_ms < 0:
            raise ValueError("WordTiming start_ms must not be negative.")
        if self.end_ms <= self.start_ms:
            raise ValueError("WordTiming end_ms must be greater than start_ms.")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("WordTiming confidence must be between 0.0 and 1.0.")
