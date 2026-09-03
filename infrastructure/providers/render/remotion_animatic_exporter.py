"""Materialize a provider-neutral animatic as Remotion props and public assets."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path, PurePosixPath

from core.domain.entities.animatic_project import AnimaticProject
from core.domain.ports.storage_port import StoragePort


class RemotionAnimaticExporter:
    _SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(
        self, storage: StoragePort, motion_public_directory: str | Path
    ) -> None:
        self._storage = storage
        self._public = Path(motion_public_directory)

    async def export(self, project: AnimaticProject) -> Path:
        if not self._SAFE_ID.fullmatch(project.id):
            raise ValueError("Animatic id is not storage-safe.")
        relative_root = PurePosixPath("anime-animatic") / project.id
        target_root = self._public / Path(*relative_root.parts)
        await asyncio.to_thread(target_root.mkdir, parents=True, exist_ok=True)
        clips = []
        for clip in project.clips:
            image_suffix = PurePosixPath(clip.image_storage_key).suffix or ".png"
            image_name = f"{clip.shot_id}{image_suffix}"
            await asyncio.to_thread(
                (target_root / image_name).write_bytes,
                await self._storage.load(clip.image_storage_key),
            )
            audio_src = ""
            if clip.dialogue_audio_storage_key:
                audio_suffix = (
                    PurePosixPath(clip.dialogue_audio_storage_key).suffix or ".wav"
                )
                audio_name = f"{clip.shot_id}{audio_suffix}"
                await asyncio.to_thread(
                    (target_root / audio_name).write_bytes,
                    await self._storage.load(clip.dialogue_audio_storage_key),
                )
                audio_src = f"{relative_root.as_posix()}/{audio_name}"
            clips.append(
                {
                    "shotId": clip.shot_id,
                    "startFrame": clip.start_frame,
                    "durationFrames": clip.duration_frames,
                    "imageSrc": f"{relative_root.as_posix()}/{image_name}",
                    "dialogue": clip.dialogue,
                    "audioSrc": audio_src,
                }
            )
        props = {
            "title": "SELMA Anime Animatic",
            "fps": project.fps,
            "durationInFrames": project.duration_in_frames,
            "clips": clips,
        }
        target = target_root / "props.json"
        temporary = target_root / f".props.{uuid.uuid4().hex}.tmp"
        payload = json.dumps(props, ensure_ascii=False, indent=2)
        try:
            await asyncio.to_thread(temporary.write_text, payload, encoding="utf-8")
            await asyncio.to_thread(os.replace, temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target
