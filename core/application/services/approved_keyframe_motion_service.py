from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from core.application.services.candidate.candidate_evaluation_service import (
    CandidateEvaluationService,
)
from core.domain.entities.candidate.keyframe_candidate import CandidateStatus
from core.domain.entities.shot_motion_clip import ShotMotionClip
from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import MotionGenerationError, StorageError
from core.domain.ports.image_to_video_generation_port import ImageToVideoGenerationPort
from core.domain.ports.shot_motion_clip_repository_port import (
    ShotMotionClipRepositoryPort,
)
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.image_to_video_request import ImageToVideoRequest
from core.domain.value_objects.render_profile import RenderProfile


class ApprovedKeyframeMotionService:
    """Animate only the human-approved frame committed by the A7 gate."""

    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    _CONTENT_TYPES = {"video/mp4": ".mp4", "video/webm": ".webm"}

    def __init__(
        self,
        *,
        generator: ImageToVideoGenerationPort,
        storage: StoragePort,
        candidates: CandidateEvaluationService,
        clips: ShotMotionClipRepositoryPort,
    ) -> None:
        self._generator = generator
        self._storage = storage
        self._candidates = candidates
        self._clips = clips

    @property
    def provider_name(self) -> str:
        return self._generator.name

    async def generate(
        self,
        *,
        storyboard: ShotStoryboard,
        target_duration_seconds: float,
        motion_prompt: str,
        camera_motion: str = "static",
        width: int = 1024,
        height: int = 576,
        fps: float = 24.0,
        seed: int | None = None,
        sampling_steps: int = 12,
        guidance_scale: float = 4.5,
        render_profile: RenderProfile = RenderProfile.BALANCED,
    ) -> ShotMotionClip:
        if not self._SAFE_ID.fullmatch(storyboard.shot_contract_id):
            raise MotionGenerationError("Shot contract ID is not storage-key safe.")
        candidate = await self._candidates.get_approved_candidate_for_shot(
            storyboard.shot_contract_id
        )
        if candidate is None or candidate.status != CandidateStatus.COMMITTED:
            raise MotionGenerationError(
                "Image-to-video requires a candidate committed through the human-review gate."
            )
        matching_frames = [
            frame
            for frame in storyboard.frames
            if frame.storage_key == candidate.storage_key
        ]
        if len(matching_frames) != 1:
            raise MotionGenerationError(
                "Storyboard does not contain exactly one frame for the committed candidate."
            )
        frame = matching_frames[0]
        if not await self._storage.exists(frame.storage_key):
            raise StorageError(
                f"Committed storyboard image '{frame.storage_key}' was not found."
            )
        request = ImageToVideoRequest(
            shot_contract_id=storyboard.shot_contract_id,
            storyboard_id=storyboard.id,
            storyboard_frame_id=frame.id,
            source_image_storage_key=frame.storage_key,
            target_duration_seconds=target_duration_seconds,
            motion_prompt=motion_prompt,
            camera_motion=camera_motion,
            width=width,
            height=height,
            fps=fps,
            seed=seed,
            sampling_steps=sampling_steps,
            guidance_scale=guidance_scale,
            render_profile=render_profile,
        )
        generated = await self._generator.generate_video(request)
        self._validate_generated_video(generated.video_bytes, generated.content_type)
        if (
            generated.width <= 0
            or generated.height <= 0
            or generated.duration_seconds <= 0
            or generated.fps <= 0
        ):
            raise MotionGenerationError("Provider returned invalid video properties.")

        clip_id = str(uuid.uuid4())
        extension = self._CONTENT_TYPES[generated.content_type]
        storage_key = (
            f"motion/{storyboard.shot_contract_id}/clips/{clip_id}{extension}"
        )
        stored = await self._storage.save(
            storage_key, generated.video_bytes, generated.content_type
        )
        if stored.key != storage_key:
            raise StorageError("Storage adapter returned a different key for the motion clip.")
        clip = ShotMotionClip(
            id=clip_id,
            shot_contract_id=storyboard.shot_contract_id,
            storyboard_id=storyboard.id,
            storyboard_frame_id=frame.id,
            candidate_id=candidate.id,
            source_image_storage_key=frame.storage_key,
            storage_key=storage_key,
            content_type=generated.content_type,
            provider=self._generator.name,
            provider_asset_id=generated.provider_asset_id,
            width=generated.width,
            height=generated.height,
            duration_seconds=generated.duration_seconds,
            fps=generated.fps,
            created_at=datetime.now(timezone.utc),
            render_profile=render_profile.value,
        )
        await self._clips.save(clip)
        return clip

    def _validate_generated_video(self, data: bytes, content_type: str) -> None:
        if not data:
            raise MotionGenerationError("Provider returned empty video bytes.")
        if content_type not in self._CONTENT_TYPES:
            raise MotionGenerationError(
                f"Provider returned unsupported video content type: {content_type}"
            )
        valid = (
            content_type == "video/mp4" and len(data) >= 12 and data[4:8] == b"ftyp"
        ) or (content_type == "video/webm" and data.startswith(b"\x1aE\xdf\xa3"))
        if not valid:
            raise MotionGenerationError(
                "Provider bytes do not match the declared video content type."
            )
