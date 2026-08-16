from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackgroundTrack:
    file_path: str
    title: str
    attribution: str
    license: str
    themes: list[str]
    source_url: str = ""
    sha256: str = ""
    evidence_reference: str = ""
    commercial_use: bool = True
    youtube_allowed: bool = True
    attribution_required: bool = True
