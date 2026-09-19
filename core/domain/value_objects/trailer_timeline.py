"""Deterministic trailer frame budget and beat contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.domain.exceptions import PreProductionValidationError
from core.domain.value_objects.trailer_brief import TrailerBrief


@dataclass(frozen=True)
class TrailerBeat:
    beat_id: str
    title: str
    start_frame: int
    end_frame: int
    purpose: str

    def __post_init__(self) -> None:
        if not self.beat_id.strip() or not self.title.strip() or not self.purpose.strip():
            raise PreProductionValidationError("Trailer beat identity and purpose are required.")
        if self.start_frame < 0 or self.end_frame <= self.start_frame:
            raise PreProductionValidationError("Trailer beat frame range is invalid.")

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    def to_dict(self) -> dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "title": self.title,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "duration_frames": self.duration_frames,
            "purpose": self.purpose,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrailerBeat:
        return cls(
            beat_id=str(data.get("beat_id", "")),
            title=str(data.get("title", "")),
            start_frame=int(data.get("start_frame", -1)),
            end_frame=int(data.get("end_frame", 0)),
            purpose=str(data.get("purpose", "")),
        )


@dataclass(frozen=True)
class TrailerTimeline:
    trailer_id: str
    fps: int
    duration_frames: int
    beats: tuple[TrailerBeat, ...]

    @classmethod
    def from_brief(cls, brief: TrailerBrief) -> TrailerTimeline:
        boundaries = (0, 912, 2064, 3624, 4320)
        labels = (
            ("normal-world", "Normal dünya ve rahatsızlık", "Dünyayı ve ilk huzursuzluğu kur."),
            ("perceptual-collapse", "Salgın ve algısal çözülme", "FHD-80/LIMEN gizemini derinleştir."),
            ("action-threat", "Aksiyon ve LIMEN tehdidi", "Tehdidi ve karakter seçimlerini yükselt."),
            ("silence-hook", "Sessizlik, kanca, title card", "Duygusal kırılma ve başlık vuruşu."),
        )
        beats = tuple(
            TrailerBeat(beat_id=beat_id, title=title, start_frame=boundaries[index], end_frame=boundaries[index + 1], purpose=purpose)
            for index, (beat_id, title, purpose) in enumerate(labels)
        )
        return cls(brief.trailer_id, brief.fps, brief.duration_frames, beats)

    def __post_init__(self) -> None:
        if self.fps != 24 or self.duration_frames != 4320 or not self.beats:
            raise PreProductionValidationError("Trailer timeline requires 4320 frames at 24 FPS.")
        expected = 0
        for beat in self.beats:
            if beat.start_frame != expected:
                raise PreProductionValidationError("Trailer beats must be contiguous and ordered.")
            expected = beat.end_frame
        if expected != self.duration_frames:
            raise PreProductionValidationError("Trailer beats must cover the complete trailer.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "trailer_id": self.trailer_id,
            "fps": self.fps,
            "duration_frames": self.duration_frames,
            "duration_seconds": self.duration_frames / self.fps,
            "beats": [beat.to_dict() for beat in self.beats],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrailerTimeline:
        return cls(
            trailer_id=str(data.get("trailer_id", "")),
            fps=int(data.get("fps", 0)),
            duration_frames=int(data.get("duration_frames", 0)),
            beats=tuple(TrailerBeat.from_dict(item) for item in data.get("beats", ()) if isinstance(item, Mapping)),
        )
