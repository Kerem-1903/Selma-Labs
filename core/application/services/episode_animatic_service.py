"""Build a reviewable animatic from an Episode Director plan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from core.domain.entities.animatic_project import AnimaticClip, AnimaticProject
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.episode_director_plan import EpisodeDirectorPlan

AnimaticRenderMode = Literal["STRICT", "PLACEHOLDER"]


@dataclass(frozen=True)
class EpisodeAnimaticResult:
    """Resolved animatic project or a deterministic pre-render failure."""

    status: str
    project: AnimaticProject | None
    mode: AnimaticRenderMode = "STRICT"
    missing_assets: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"READY_FOR_REVIEW", "PLANNED", "BLOCKED"}:
            raise ValueError(f"Unknown episode animatic status: {self.status}")
        if self.mode not in {"STRICT", "PLACEHOLDER"}:
            raise ValueError(f"Unknown animatic render mode: {self.mode}")
        if self.project is not None and self.status != "READY_FOR_REVIEW":
            raise ValueError("An animatic project is only valid when ready for review.")
        if self.status == "BLOCKED" and self.mode != "STRICT":
            raise ValueError("Only strict animatics may be blocked before rendering.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "missing_assets": list(self.missing_assets),
            "warnings": list(self.warnings),
            "animatic_project": self.project.to_dict() if self.project else None,
        }


class EpisodeAnimaticService:
    """Resolve plan decisions into the existing human-reviewable animatic model."""

    def __init__(self, storage: StoragePort) -> None:
        self._storage = storage

    async def build(
        self,
        plan: EpisodeDirectorPlan,
        *,
        dialogue_audio_keys: Mapping[str, str] | None = None,
        mode: AnimaticRenderMode = "STRICT",
    ) -> EpisodeAnimaticResult:
        """Resolve assets without allowing missing media to masquerade as success.

        ``STRICT`` stops before creating a project when a visual or dialogue
        audio asset is absent. ``PLACEHOLDER`` creates a reviewable project and
        marks each unavailable input with a visible placeholder warning that
        the Remotion exporter can render.
        """
        if mode not in {"STRICT", "PLACEHOLDER"}:
            raise ValueError("Animatic mode must be STRICT or PLACEHOLDER.")

        audio_keys = dialogue_audio_keys or {}
        missing: list[str] = []
        warnings: list[str] = []
        clips: list[AnimaticClip] = []
        start_frame = 0

        for scene in plan.scenes:
            for shot in scene.shots:
                image_key = shot.background_asset_ref or shot.character_pose_asset_ref
                visual_missing = False
                if not image_key:
                    missing.append(f"{shot.shot_id}:visual_asset")
                    visual_missing = True
                elif not await self._storage.exists(image_key):
                    missing.append(f"{shot.shot_id}:{image_key}")
                    visual_missing = True

                audio_key = str(audio_keys.get(shot.shot_id, "")).strip()
                audio_missing = False
                if shot.dialogue:
                    if not audio_key:
                        missing.append(f"{shot.shot_id}:dialogue_audio")
                        audio_missing = True
                    elif not await self._storage.exists(audio_key):
                        missing.append(f"{shot.shot_id}:{audio_key}")
                        audio_missing = True

                duration_frames = (
                    shot.duration_frames
                    if shot.duration_frames is not None
                    else max(1, round(shot.duration_seconds * plan.fps))
                )
                if mode == "PLACEHOLDER":
                    if visual_missing:
                        image_key = f"placeholder://{shot.shot_id}/visual"
                        warnings.append(
                            f"{shot.shot_id}: visual asset is missing; placeholder card will be rendered."
                        )
                    if audio_missing:
                        warnings.append(
                            f"{shot.shot_id}: dialogue audio is missing; placeholder warning will be rendered."
                        )
                    clips.append(
                        AnimaticClip(
                            shot_id=shot.shot_id,
                            start_frame=start_frame,
                            duration_frames=duration_frames,
                            image_storage_key=image_key,
                            dialogue=shot.dialogue if not audio_missing else "",
                            dialogue_audio_storage_key=audio_key if not audio_missing else "",
                            warning=(
                                "MISSING VISUAL ASSET"
                                if visual_missing and not audio_missing
                                else "MISSING DIALOGUE AUDIO"
                                if audio_missing and not visual_missing
                                else "MISSING VISUAL + DIALOGUE AUDIO"
                                if visual_missing
                                else ""
                            ),
                        )
                    )
                elif not visual_missing and not audio_missing:
                    clips.append(
                        AnimaticClip(
                            shot_id=shot.shot_id,
                            start_frame=start_frame,
                            duration_frames=duration_frames,
                            image_storage_key=image_key,
                            dialogue=shot.dialogue,
                            dialogue_audio_storage_key=audio_key,
                        )
                    )
                start_frame += duration_frames

        unique_missing = tuple(dict.fromkeys(missing))
        if unique_missing and mode == "STRICT":
            return EpisodeAnimaticResult(
                status="BLOCKED",
                project=None,
                mode="STRICT",
                missing_assets=unique_missing,
                warnings=(
                    "Strict animatic render was not started because required assets are missing or unapproved.",
                ),
            )

        project = AnimaticProject.create(
            production_plan_id=plan.episode_id,
            clips=tuple(clips),
            fps=plan.fps,
        )
        return EpisodeAnimaticResult(
            status="READY_FOR_REVIEW",
            project=project,
            mode=mode,
            missing_assets=unique_missing,
            warnings=tuple(warnings),
        )
