"""Auditable text preparation applied immediately before voice synthesis."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NarrationPreparation:
    spoken_text: str
    language: str
    replacements: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.spoken_text.strip():
            raise ValueError("Prepared narration must not be empty.")
        if self.language not in {"tr", "en"}:
            raise ValueError("Narration preparation supports Turkish or English.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "spoken_text": self.spoken_text,
            "language": self.language,
            "replacements": [
                {"source": source, "spoken": spoken}
                for source, spoken in self.replacements
            ],
        }
