from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.domain.value_objects.background_track import BackgroundTrack


@dataclass(frozen=True)
class MusicSelectionDecision:
    theme: str
    confidence: float
    rationale: str
    track: BackgroundTrack
    overridden: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "track_title": self.track.title,
            "track_file_path": self.track.file_path,
            "track_attribution": self.track.attribution,
            "track_license": self.track.license,
            "track_themes": list(self.track.themes),
            "track_source_url": self.track.source_url,
            "track_sha256": self.track.sha256,
            "track_evidence_reference": self.track.evidence_reference,
            "track_commercial_use": self.track.commercial_use,
            "track_youtube_allowed": self.track.youtube_allowed,
            "track_attribution_required": self.track.attribution_required,
            "overridden": self.overridden,
        }
