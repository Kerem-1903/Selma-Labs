from __future__ import annotations

from core.domain.exceptions import MotionGenerationError
from core.domain.ports.lipsync_port import LipSyncPort
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.portable_storage_key import PortableStorageKey
from infrastructure.storage.local_fs_storage import LocalFsStorage


class LivePortraitAdapter(LipSyncPort):
    """Storage-backed LivePortrait boundary.

    The current adapter is deliberately a mock/passthrough: it verifies both
    inputs and persists a valid copy of the source clip. It never claims that
    mouth animation was performed, which keeps local development deterministic
    until the LivePortrait runtime is connected.
    """

    def __init__(
        self,
        output_dir: str = "cache/lipsync",
        *,
        storage: StoragePort | None = None,
    ) -> None:
        self._storage = storage or LocalFsStorage(output_dir)

    @property
    def name(self) -> str:
        return "liveportrait:mock-passthrough"

    async def generate_lipsync_clip(
        self,
        source_image_or_video_path: str,
        audio_path: str,
        output_video_path: str,
    ) -> str:
        for value, label in (
            (source_image_or_video_path, "source video"),
            (audio_path, "dialogue audio"),
            (output_video_path, "output video"),
        ):
            self._validate_key(value, label)
        if not await self._storage.exists(source_image_or_video_path):
            raise MotionGenerationError(
                f"LivePortrait source '{source_image_or_video_path}' was not found."
            )
        if not await self._storage.exists(audio_path):
            raise MotionGenerationError(
                f"LivePortrait audio '{audio_path}' was not found."
            )
        video_bytes = await self._storage.load(source_image_or_video_path)
        audio_bytes = await self._storage.load(audio_path)
        if not video_bytes or not audio_bytes:
            raise MotionGenerationError("LivePortrait inputs must not be empty.")
        suffix = PortableStorageKey(source_image_or_video_path).suffix
        content_type = {".mp4": "video/mp4", ".webm": "video/webm"}.get(suffix)
        if content_type is None:
            raise MotionGenerationError("LivePortrait source must be MP4 or WebM.")
        valid_video = (
            content_type == "video/mp4"
            and len(video_bytes) >= 12
            and video_bytes[4:8] == b"ftyp"
        ) or (
            content_type == "video/webm"
            and video_bytes.startswith(b"\x1aE\xdf\xa3")
        )
        if not valid_video:
            raise MotionGenerationError("LivePortrait source is not a valid video container.")
        output_suffix = PortableStorageKey(output_video_path).suffix
        if output_suffix != suffix:
            raise MotionGenerationError(
                "Mock LivePortrait output must keep the source video format."
            )
        stored = await self._storage.save(output_video_path, video_bytes, content_type)
        if stored.key != output_video_path:
            raise MotionGenerationError("Storage adapter changed the lip-sync output key.")
        return stored.key

    @staticmethod
    def _validate_key(value: str, label: str) -> None:
        try:
            PortableStorageKey(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"LivePortrait {label} must be a portable storage key."
            ) from error
