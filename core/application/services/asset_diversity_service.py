"""Perceptual clip selection and finite reuse budgets for Shorts timelines."""
from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from typing import Sequence

from PIL import Image, UnidentifiedImageError

from core.domain.exceptions import AssetDiversityError
from core.domain.entities.media_asset import MediaAsset
from core.domain.ports.frame_extraction_port import FrameExtractionPort
from core.domain.value_objects.asset_diversity import AssetUsage
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.visual_intent import VisualIntent


class AssetDiversityService:
    """Select the strongest relevant candidate that adds a real visual phase."""

    def __init__(
        self,
        *,
        perceptual_distance_threshold: int = 7,
        maximum_asset_uses: int = 2,
        maximum_pose_uses: int = 2,
        maximum_camera_angle_uses: int = 2,
        maximum_background_uses: int = 3,
        frame_extractor: FrameExtractionPort | None = None,
        representative_frame_count: int = 3,
    ) -> None:
        if perceptual_distance_threshold < 0:
            raise ValueError("perceptual_distance_threshold must not be negative.")
        if min(
            maximum_asset_uses,
            maximum_pose_uses,
            maximum_camera_angle_uses,
            maximum_background_uses,
        ) <= 0:
            raise ValueError("Asset diversity reuse budgets must be positive.")
        if representative_frame_count <= 0:
            raise ValueError("representative_frame_count must be positive.")
        self._distance_threshold = perceptual_distance_threshold
        self._maximum_asset_uses = maximum_asset_uses
        self._maximum_pose_uses = maximum_pose_uses
        self._maximum_camera_angle_uses = maximum_camera_angle_uses
        self._maximum_background_uses = maximum_background_uses
        self._frame_extractor = frame_extractor
        self._representative_frame_count = representative_frame_count

    def select(
        self,
        intent: VisualIntent,
        candidates: Sequence[ScoredAsset],
        history: Sequence[AssetUsage],
    ) -> tuple[ScoredAsset, AssetUsage]:
        """Choose by quality order while rejecting cosmetic-only variety."""
        rejection_reasons: list[str] = []
        for candidate in candidates:
            usage = self._usage(intent, candidate)
            reason = self._rejection_reason(usage, history)
            if reason is None:
                return candidate, usage
            rejection_reasons.append(f"{candidate.asset.id}: {reason}")
        details = "; ".join(rejection_reasons) or "no scored candidates"
        raise AssetDiversityError(
            "No relevant candidate satisfied the perceptual diversity policy: "
            f"{details}."
        )

    async def refine_downloaded_usage(
        self,
        asset: MediaAsset,
        usage: AssetUsage,
    ) -> AssetUsage:
        """Replace thumbnail evidence with representative frames from the real clip."""
        if self._frame_extractor is None:
            return usage
        frames = await self._frame_extractor.extract_frames(
            asset,
            self._representative_frame_count,
        )
        hashes = self.fingerprint_frames(frames)
        if not hashes:
            return usage
        return replace(
            usage,
            perceptual_hashes=tuple(
                dict.fromkeys((*usage.perceptual_hashes, *hashes))
            ),
            motion_energy=self.motion_energy_from_frames(
                frames,
                fallback=usage.motion_energy,
            ),
        )

    def validate_usage(
        self,
        usage: AssetUsage,
        history: Sequence[AssetUsage],
    ) -> None:
        reason = self._rejection_reason(usage, history)
        if reason is not None:
            raise AssetDiversityError(
                f"Downloaded asset '{usage.asset_id}' failed diversity validation: {reason}."
            )

    def _rejection_reason(
        self,
        usage: AssetUsage,
        history: Sequence[AssetUsage],
    ) -> str | None:
        identical = [
            previous
            for previous in history
            if previous.asset_id == usage.asset_id
            or self.perceptually_similar(previous.perceptual_hashes, usage.perceptual_hashes)
        ]
        if identical:
            previous = identical[-1]
            if previous == history[-1]:
                return "immediate perceptual repeat"
            if not self._materially_different(previous, usage):
                return "same imagery without a different visual function"
            if sum(previous.asset_id == usage.asset_id for previous in history) >= self._maximum_asset_uses:
                return "source asset reuse budget exhausted"

        if usage.subject_pose and self._count(history, "subject_pose", usage.subject_pose) >= self._maximum_pose_uses:
            return "subject-pose reuse budget exhausted"
        if usage.camera_angle and self._count(history, "camera_angle", usage.camera_angle) >= self._maximum_camera_angle_uses:
            return "camera-angle reuse budget exhausted"
        if (
            usage.background_signature
            and self._count(history, "background_signature", usage.background_signature)
            >= self._maximum_background_uses
        ):
            return "background reuse budget exhausted"
        return None

    @staticmethod
    def _materially_different(previous: AssetUsage, current: AssetUsage) -> bool:
        return bool(
            previous.visual_job != current.visual_job
            or previous.shot_type != current.shot_type
            or previous.explanation_mode != current.explanation_mode
            or previous.overlay_labels != current.overlay_labels
        )

    @staticmethod
    def _count(history: Sequence[AssetUsage], field: str, value: str) -> int:
        return sum(getattr(previous, field) == value for previous in history)

    @classmethod
    def _usage(cls, intent: VisualIntent, candidate: ScoredAsset) -> AssetUsage:
        metadata = candidate.asset.metadata or {}
        evidence = metadata.get("vision_evidence") or {}
        return AssetUsage(
            asset_id=candidate.asset.id,
            perceptual_hashes=tuple(metadata.get("perceptual_hashes") or ()),
            visual_job=intent.visual_job,
            shot_type=intent.shot_type,
            explanation_mode=intent.explanation_mode,
            overlay_labels=intent.overlay_labels,
            subject_pose=str(
                metadata.get("subject_pose")
                or evidence.get("subject_pose")
                or ""
            ).casefold(),
            camera_angle=str(
                metadata.get("camera_angle")
                or evidence.get("camera_angle")
                or intent.shot_type
            ).casefold(),
            background_signature=str(
                metadata.get("background_signature")
                or evidence.get("background_signature")
                or evidence.get("scene_type")
                or ""
            ).casefold(),
            motion_energy=float(metadata.get("motion_energy", 0.5)),
            start_ms=intent.start_ms,
            end_ms=intent.end_ms,
        )

    @classmethod
    def fingerprint_frames(cls, frames: Sequence[bytes]) -> tuple[str, ...]:
        """Return crop-aware difference hashes for representative frames."""
        hashes: list[str] = []
        for frame in frames:
            try:
                with Image.open(BytesIO(frame)) as image:
                    grayscale = image.convert("L")
                    for ratio in (1.0, 0.80, 0.60):
                        crop = cls._center_crop(grayscale, ratio)
                        hashes.append(cls._difference_hash(crop))
            except (OSError, UnidentifiedImageError):
                continue
        return tuple(dict.fromkeys(hashes))

    @staticmethod
    def _center_crop(image: Image.Image, ratio: float) -> Image.Image:
        width, height = image.size
        crop_width = max(1, round(width * ratio))
        crop_height = max(1, round(height * ratio))
        left = (width - crop_width) // 2
        top = (height - crop_height) // 2
        return image.crop((left, top, left + crop_width, top + crop_height))

    @staticmethod
    def _difference_hash(image: Image.Image) -> str:
        import numpy as np
        resized = image.resize((9, 8), Image.Resampling.LANCZOS)
        # Replacing getdata() with numpy array representation to avoid deprecation warnings
        pixels = np.array(resized).flatten()
        value = 0
        for row in range(8):
            for column in range(8):
                left = pixels[row * 9 + column]
                right = pixels[row * 9 + column + 1]
                value = (value << 1) | int(left > right)
        return f"{value:016x}"

    def perceptually_similar(
        self,
        left: Sequence[str],
        right: Sequence[str],
    ) -> bool:
        if not left or not right:
            return False
        return min(
            (int(a, 16) ^ int(b, 16)).bit_count()
            for a in left
            for b in right
        ) <= self._distance_threshold

    @classmethod
    def motion_energy_from_frames(
        cls,
        frames: Sequence[bytes],
        *,
        fallback: float = 0.5,
    ) -> float:
        """Estimate real visual change from representative full-frame hashes."""
        hashes = [
            frame_hashes[0]
            for frame in frames
            if (frame_hashes := cls.fingerprint_frames([frame]))
        ]
        if len(hashes) < 2:
            return max(0.0, min(1.0, fallback))
        distances = [
            (int(left, 16) ^ int(right, 16)).bit_count()
            for left, right in zip(hashes, hashes[1:])
        ]
        return round(min(1.0, (sum(distances) / len(distances)) / 24.0), 4)
