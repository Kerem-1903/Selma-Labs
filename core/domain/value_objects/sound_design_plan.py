"""Provider-neutral, time-coded plan for a complete audio production."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_CUE_KINDS = {
    "hook_impact",
    "transition",
    "mechanism",
    "reveal",
    "payoff",
    "warning",
}
_AMBIENCE_PROFILES = {"none", "laboratory", "space", "nature", "tension"}


@dataclass(frozen=True)
class AudioCue:
    timestamp_ms: int
    kind: str
    duration_ms: int
    gain_db: float
    rationale: str

    def __post_init__(self) -> None:
        if self.timestamp_ms < 0:
            raise ValueError("Audio cue timestamp must not be negative.")
        if self.kind not in _CUE_KINDS:
            raise ValueError(f"Unsupported audio cue kind: {self.kind!r}.")
        if not 80 <= self.duration_ms <= 1_500:
            raise ValueError("Audio cue duration must be between 80 and 1500ms.")
        if not -36.0 <= self.gain_db <= -8.0:
            raise ValueError("Audio cue gain must be between -36 and -8 dB.")
        if not self.rationale.strip():
            raise ValueError("Audio cues require an editorial rationale.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "kind": self.kind,
            "duration_ms": self.duration_ms,
            "gain_db": self.gain_db,
            "rationale": self.rationale,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "AudioCue":
        return AudioCue(
            timestamp_ms=int(data["timestamp_ms"]),
            kind=str(data["kind"]),
            duration_ms=int(data["duration_ms"]),
            gain_db=float(data["gain_db"]),
            rationale=str(data["rationale"]),
        )


@dataclass(frozen=True)
class MusicAutomationPoint:
    timestamp_ms: int
    relative_gain_db: float
    purpose: str

    def __post_init__(self) -> None:
        if self.timestamp_ms < 0:
            raise ValueError("Music automation timestamp must not be negative.")
        if not -18.0 <= self.relative_gain_db <= 3.0:
            raise ValueError("Relative music gain must be between -18 and +3 dB.")
        if not self.purpose.strip():
            raise ValueError("Music automation points require a purpose.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_ms": self.timestamp_ms,
            "relative_gain_db": self.relative_gain_db,
            "purpose": self.purpose,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "MusicAutomationPoint":
        return MusicAutomationPoint(
            timestamp_ms=int(data["timestamp_ms"]),
            relative_gain_db=float(data["relative_gain_db"]),
            purpose=str(data["purpose"]),
        )


@dataclass(frozen=True)
class SoundDesignPlan:
    duration_ms: int
    ambience_profile: str
    cues: tuple[AudioCue, ...]
    music_automation: tuple[MusicAutomationPoint, ...]
    minimum_cue_gap_ms: int = 650
    target_integrated_lufs: float = -14.0
    target_true_peak_dbfs: float = -1.5

    def __post_init__(self) -> None:
        if self.duration_ms <= 0:
            raise ValueError("Sound design duration must be positive.")
        if self.ambience_profile not in _AMBIENCE_PROFILES:
            raise ValueError("Unsupported ambience profile.")
        if self.minimum_cue_gap_ms < 400:
            raise ValueError("Audio cue spacing must be at least 400ms.")
        if not -16.0 <= self.target_integrated_lufs <= -13.0:
            raise ValueError("Integrated loudness target must be between -16 and -13 LUFS.")
        if not -2.0 <= self.target_true_peak_dbfs <= -1.0:
            raise ValueError("True-peak target must be between -2 and -1 dBFS.")
        ordered_cues = tuple(sorted(self.cues, key=lambda cue: cue.timestamp_ms))
        if ordered_cues != self.cues:
            raise ValueError("Audio cues must be ordered by timestamp.")
        if any(cue.timestamp_ms + cue.duration_ms > self.duration_ms + 50 for cue in self.cues):
            raise ValueError("An audio cue exceeds the production duration.")
        if any(
            right.timestamp_ms - left.timestamp_ms < self.minimum_cue_gap_ms
            for left, right in zip(self.cues, self.cues[1:])
        ):
            raise ValueError("Audio cues violate the minimum spacing policy.")
        ordered_music = tuple(
            sorted(self.music_automation, key=lambda point: point.timestamp_ms)
        )
        if ordered_music != self.music_automation:
            raise ValueError("Music automation points must be ordered by timestamp.")
        if any(point.timestamp_ms > self.duration_ms for point in self.music_automation):
            raise ValueError("Music automation exceeds the production duration.")

    @property
    def semantic_kinds(self) -> frozenset[str]:
        return frozenset(cue.kind for cue in self.cues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "duration_ms": self.duration_ms,
            "ambience_profile": self.ambience_profile,
            "cues": [cue.to_dict() for cue in self.cues],
            "music_automation": [point.to_dict() for point in self.music_automation],
            "minimum_cue_gap_ms": self.minimum_cue_gap_ms,
            "target_integrated_lufs": self.target_integrated_lufs,
            "target_true_peak_dbfs": self.target_true_peak_dbfs,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SoundDesignPlan":
        return SoundDesignPlan(
            duration_ms=int(data["duration_ms"]),
            ambience_profile=str(data.get("ambience_profile") or "none"),
            cues=tuple(AudioCue.from_dict(dict(item)) for item in data.get("cues", [])),
            music_automation=tuple(
                MusicAutomationPoint.from_dict(dict(item))
                for item in data.get("music_automation", [])
            ),
            minimum_cue_gap_ms=int(data.get("minimum_cue_gap_ms", 650)),
            target_integrated_lufs=float(data.get("target_integrated_lufs", -14.0)),
            target_true_peak_dbfs=float(data.get("target_true_peak_dbfs", -1.5)),
        )
