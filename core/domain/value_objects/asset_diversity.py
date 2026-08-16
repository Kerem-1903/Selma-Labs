"""Perceptual identity and editorial usage metadata for selected footage."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssetUsage:
    """One selected clip phase and the evidence used to control repetition."""

    asset_id: str
    perceptual_hashes: tuple[str, ...]
    visual_job: str
    shot_type: str
    explanation_mode: str
    overlay_labels: tuple[str, ...]
    subject_pose: str = ""
    camera_angle: str = ""
    background_signature: str = ""
    motion_energy: float = 0.5
    start_ms: int = 0
    end_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "perceptual_hashes": list(self.perceptual_hashes),
            "visual_job": self.visual_job,
            "shot_type": self.shot_type,
            "explanation_mode": self.explanation_mode,
            "overlay_labels": list(self.overlay_labels),
            "subject_pose": self.subject_pose,
            "camera_angle": self.camera_angle,
            "background_signature": self.background_signature,
            "motion_energy": self.motion_energy,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "AssetUsage":
        return AssetUsage(
            asset_id=str(data["asset_id"]),
            perceptual_hashes=tuple(str(value) for value in data.get("perceptual_hashes", [])),
            visual_job=str(data.get("visual_job") or "support_context"),
            shot_type=str(data.get("shot_type") or "medium"),
            explanation_mode=str(data.get("explanation_mode") or "stock"),
            overlay_labels=tuple(str(value) for value in data.get("overlay_labels", [])),
            subject_pose=str(data.get("subject_pose") or ""),
            camera_angle=str(data.get("camera_angle") or ""),
            background_signature=str(data.get("background_signature") or ""),
            motion_energy=float(data.get("motion_energy", 0.5)),
            start_ms=int(data.get("start_ms", 0)),
            end_ms=int(data.get("end_ms", 0)),
        )


@dataclass(frozen=True)
class EditorialRhythmReport:
    """Machine-verifiable evidence that the edit follows its information beats."""

    beat_aligned: bool
    immediate_opening: bool
    semantic_transitions: int
    explanatory_interrupts: int
    low_motion_exceptions: tuple[int, ...] = ()
    unresolved_low_motion: tuple[int, ...] = ()
    loop_closure_ready: bool = False

    @property
    def passed(self) -> bool:
        return (
            self.beat_aligned
            and self.immediate_opening
            and not self.unresolved_low_motion
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "beat_aligned": self.beat_aligned,
            "immediate_opening": self.immediate_opening,
            "semantic_transitions": self.semantic_transitions,
            "explanatory_interrupts": self.explanatory_interrupts,
            "low_motion_exceptions": list(self.low_motion_exceptions),
            "unresolved_low_motion": list(self.unresolved_low_motion),
            "loop_closure_ready": self.loop_closure_ready,
            "passed": self.passed,
        }
