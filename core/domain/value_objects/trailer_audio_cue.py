"""Timeline-bound music and SFX cue metadata for trailer mixes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.domain.exceptions import PreProductionValidationError


@dataclass(frozen=True)
class TrailerAudioCue:
    cue_id: str
    kind: str
    storage_key: str
    start_frame: int
    end_frame: int
    gain_db: float = 0.0
    fade_in_frames: int = 0
    fade_out_frames: int = 0
    ducking_db: float = 0.0

    def __post_init__(self) -> None:
        if not self.cue_id.strip() or not self.storage_key.strip():
            raise PreProductionValidationError("Trailer audio cue identity and storage key are required.")
        if self.kind not in {"MUSIC", "SFX"}:
            raise PreProductionValidationError("Trailer audio cue kind must be MUSIC or SFX.")
        if self.start_frame < 0 or self.end_frame <= self.start_frame:
            raise PreProductionValidationError("Trailer audio cue frame range is invalid.")
        if self.fade_in_frames < 0 or self.fade_out_frames < 0:
            raise PreProductionValidationError("Trailer audio cue fades cannot be negative.")
        if self.fade_in_frames + self.fade_out_frames > self.duration_frames:
            raise PreProductionValidationError("Trailer audio cue fades exceed its frame window.")
        if self.ducking_db > 0:
            raise PreProductionValidationError("Ducking must be zero or a negative dB value.")

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    def to_dict(self) -> dict[str, Any]:
        return {
            "cue_id": self.cue_id,
            "kind": self.kind,
            "storage_key": self.storage_key,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "duration_frames": self.duration_frames,
            "gain_db": self.gain_db,
            "fade_in_frames": self.fade_in_frames,
            "fade_out_frames": self.fade_out_frames,
            "ducking_db": self.ducking_db,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrailerAudioCue:
        return cls(
            cue_id=str(data.get("cue_id", "")),
            kind=str(data.get("kind", "")),
            storage_key=str(data.get("storage_key", "")),
            start_frame=int(data.get("start_frame", -1)),
            end_frame=int(data.get("end_frame", 0)),
            gain_db=float(data.get("gain_db", 0.0)),
            fade_in_frames=int(data.get("fade_in_frames", 0)),
            fade_out_frames=int(data.get("fade_out_frames", 0)),
            ducking_db=float(data.get("ducking_db", 0.0)),
        )
