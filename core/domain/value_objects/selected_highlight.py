"""A scored, publishable excerpt selected from an AudioAsset."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectedHighlight:
    """The exact audio interval chosen as a hook, chorus, or beat drop.

    The selector owns scoring and rationale; application services own the
    policy that decides whether the score is high enough to continue.
    """

    audio_asset_id: str
    start_ms: int
    end_ms: int
    score: float
    selector_used: str
    hook_type: str
    rationale: str

    def __post_init__(self) -> None:
        if not self.audio_asset_id.strip():
            raise ValueError("SelectedHighlight audio_asset_id must not be empty.")
        if self.start_ms < 0:
            raise ValueError("SelectedHighlight start_ms must not be negative.")
        if self.end_ms <= self.start_ms:
            raise ValueError("SelectedHighlight end_ms must be greater than start_ms.")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("SelectedHighlight score must be between 0.0 and 1.0.")
        if not self.selector_used.strip():
            raise ValueError("SelectedHighlight selector_used must not be empty.")
        if not self.hook_type.strip():
            raise ValueError("SelectedHighlight hook_type must not be empty.")
        if not self.rationale.strip():
            raise ValueError("SelectedHighlight rationale must not be empty.")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def confidence_score(self) -> float:
        """Compatibility name for quality policies that consume confidence."""
        return self.score
