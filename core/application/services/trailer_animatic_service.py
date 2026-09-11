"""Build short, reviewable animatics from traceable trailer shots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from core.application.services.audio_timing_service import AudioTimingService
from core.domain.entities.animatic_project import AnimaticClip, AnimaticProject
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.trailer_audio_cue import TrailerAudioCue
from core.domain.value_objects.trailer_plan import TrailerPlan

TrailerAnimaticMode = Literal["STRICT", "PLACEHOLDER"]


class TrailerAnimaticService:
    """Bridge trailer editorial shots to the Remotion animatic contract."""

    def __init__(self, storage: StoragePort) -> None:
        self._storage = storage

    async def build(
        self,
        plan: TrailerPlan,
        *,
        assets: Mapping[str, Mapping[str, Any]] | None = None,
        shot_ids: Sequence[str] | None = None,
        audio_cues: Sequence[TrailerAudioCue] = (),
        mode: TrailerAnimaticMode = "STRICT",
    ) -> AnimaticProject | None:
        """Build selected trailer shots using their original frame durations.

        ``shot_ids`` is intentionally supported for the 3–5 shot smoke gate;
        omitting it builds the complete 180-second trailer timeline. Asset
        evidence is supplied by the caller after manifest/receipt validation.
        """
        if mode not in {"STRICT", "PLACEHOLDER"}:
            raise ValueError("Trailer animatic mode must be STRICT or PLACEHOLDER.")
        selected_ids = set(shot_ids) if shot_ids else None
        shots = tuple(
            shot for shot in plan.shots
            if selected_ids is None or shot.shot_id in selected_ids
        )
        if not shots:
            raise ValueError("Trailer animatic requires at least one selected shot.")
        if selected_ids is not None and len(shots) != len(selected_ids):
            missing_ids = sorted(selected_ids - {shot.shot_id for shot in shots})
            raise ValueError("Unknown trailer shot ids: " + ", ".join(missing_ids))

        asset_map, audio_diagnostics = await self.prepare_audio_assets(
            plan, assets or {}, shot_ids=shot_ids
        )
        invalid_audio = {
            item["shot_id"] for item in audio_diagnostics
            if item["status"] != "OK"
        }
        clips: list[AnimaticClip] = []
        missing: list[str] = []
        cursor = 0
        for shot in shots:
            evidence = asset_map.get(shot.shot_id, {})
            image_key = str(evidence.get("image_storage_key", "")).strip()
            audio_key = str(evidence.get("audio_storage_key", "")).strip()
            visual_missing = not image_key or not await self._storage.exists(image_key)
            # A spoken dialogue line and the MNEMOS system voice both require
            # an authoritative WAV; music/SFX cues remain editorial metadata
            # until the dedicated audio mix is attached.
            audio_required = bool(shot.dialogue or shot.system_voice)
            audio_missing = audio_required and (
                not audio_key or not await self._storage.exists(audio_key)
            )
            audio_missing = audio_missing or shot.shot_id in invalid_audio
            if visual_missing:
                missing.append(f"{shot.shot_id}:visual_asset")
            if audio_missing:
                missing.append(f"{shot.shot_id}:audio")
            if mode == "STRICT" and (visual_missing or audio_missing):
                continue

            warning = self._warning(visual_missing, audio_missing)
            clips.append(
                AnimaticClip(
                    shot_id=shot.shot_id,
                    start_frame=cursor,
                    duration_frames=shot.duration_frames,
                    image_storage_key=(
                        f"placeholder://{shot.shot_id}/visual"
                        if visual_missing else image_key
                    ),
                    dialogue="" if audio_missing else shot.dialogue,
                    dialogue_audio_storage_key="" if audio_missing else audio_key,
                    warning=warning,
                )
            )
            cursor += shot.duration_frames

        if missing and mode == "STRICT":
            return None
        return AnimaticProject.create(
            production_plan_id=plan.timeline.trailer_id,
            clips=tuple(clips),
            fps=plan.timeline.fps,
            project_kind="TRAILER",
            audio_cues=self._remap_audio_cues(audio_cues, shots, selected_ids is not None),
        )

    @staticmethod
    def _remap_audio_cues(
        audio_cues: Sequence[TrailerAudioCue],
        shots: Sequence[Any],
        compact_timeline: bool,
    ) -> tuple[dict[str, Any], ...]:
        """Map source cues onto the compact selected-shot timeline."""
        if not compact_timeline:
            return tuple(cue.to_dict() for cue in audio_cues)

        remapped: list[dict[str, Any]] = []
        for cue in audio_cues:
            spans: list[list[int]] = []
            cursor = 0
            for shot in shots:
                source_start = max(cue.start_frame, shot.start_frame)
                source_end = min(cue.end_frame, shot.end_frame)
                if source_start < source_end:
                    mapped_start = cursor + source_start - shot.start_frame
                    mapped_end = cursor + source_end - shot.start_frame
                    if (
                        spans
                        and spans[-1][1] == source_start
                        and spans[-1][3] == mapped_start
                    ):
                        spans[-1][1] = source_end
                        spans[-1][3] = mapped_end
                    else:
                        spans.append([source_start, source_end, mapped_start, mapped_end])
                cursor += shot.duration_frames

            for index, (source_start, _source_end, mapped_start, mapped_end) in enumerate(spans):
                payload = cue.to_dict()
                payload.update(
                    {
                        "cue_id": (
                            cue.cue_id
                            if len(spans) == 1
                            else f"{cue.cue_id}:segment-{index + 1:02d}"
                        ),
                        "start_frame": mapped_start,
                        "end_frame": mapped_end,
                        "duration_frames": mapped_end - mapped_start,
                        "trim_before_frames": source_start - cue.start_frame,
                        "source_duration_frames": cue.duration_frames,
                    }
                )
                remapped.append(payload)
        return tuple(remapped)

    async def prepare_audio_assets(
        self,
        plan: TrailerPlan,
        assets: Mapping[str, Mapping[str, Any]],
        *,
        shot_ids: Sequence[str] | None = None,
    ) -> tuple[dict[str, dict[str, Any]], tuple[dict[str, Any], ...]]:
        """Hash and time-check WAV bytes before they enter a trailer project.

        The caller may provide an expected ``audio_hash``, but the value used
        downstream is always calculated from the bytes loaded from storage.
        A hash mismatch and an overflow are both hard failures for STRICT mode.
        """
        selected = set(shot_ids) if shot_ids else {shot.shot_id for shot in plan.shots}
        normalized = {str(key): dict(value) for key, value in assets.items()}
        diagnostics: list[dict[str, Any]] = []
        for shot in plan.shots:
            if shot.shot_id not in selected or not (shot.dialogue or shot.system_voice):
                continue
            evidence = normalized.setdefault(shot.shot_id, {})
            key = str(evidence.get("audio_storage_key", "")).strip()
            if not key or not await self._storage.exists(key):
                diagnostics.append({"shot_id": shot.shot_id, "status": "MISSING"})
                continue
            try:
                data = await self._storage.load(key)
                actual_hash = AudioTimingService.sha256_bytes(data)
                supplied_hash = str(evidence.get("audio_hash", "")).strip().lower()
                timing = AudioTimingService.inspect_dialogue_bytes(
                    data,
                    allocated_frames=shot.duration_frames,
                    fps=plan.timeline.fps,
                )
            except (OSError, ValueError, TypeError) as error:
                diagnostics.append({
                    "shot_id": shot.shot_id,
                    "status": "INVALID",
                    "error": str(error),
                })
                continue
            evidence["audio_hash"] = actual_hash
            if supplied_hash and supplied_hash != actual_hash:
                diagnostics.append({
                    "shot_id": shot.shot_id,
                    "status": "HASH_MISMATCH",
                    "audio_hash": actual_hash,
                })
            elif timing.status != "OK":
                diagnostics.append({
                    "shot_id": shot.shot_id,
                    "status": "BLOCKED",
                    "audio_hash": actual_hash,
                    "timing": timing.to_dict(),
                })
            else:
                diagnostics.append({
                    "shot_id": shot.shot_id,
                    "status": "OK",
                    "audio_hash": actual_hash,
                    "timing": timing.to_dict(),
                })
        return normalized, tuple(diagnostics)

    @staticmethod
    def _warning(visual_missing: bool, audio_missing: bool) -> str:
        if visual_missing and audio_missing:
            return "MISSING VISUAL + DIALOGUE AUDIO"
        if visual_missing:
            return "MISSING VISUAL ASSET"
        if audio_missing:
            return "MISSING DIALOGUE AUDIO"
        return ""
