from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioMixResult:
    output_path: str
