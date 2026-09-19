"""CLI handlers for episode animatic assembly and rendering."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from core.application.services.episode_animatic_service import EpisodeAnimaticService
from core.domain.value_objects.episode_director_plan import EpisodeDirectorPlan
from infrastructure.storage.local_fs_storage import LocalFsStorage

JsonLoader = Callable[[str | Path], dict[str, Any]]
JsonWriter = Callable[[str | Path, dict[str, Any]], Path]
AwaitableRunner = Callable[[Any], Any]


def run_episode_animatic_command(
    arguments: argparse.Namespace,
    *,
    load_json_object: JsonLoader,
    write_json: JsonWriter,
    awaitable_run: AwaitableRunner,
) -> int:
    """Build an episode animatic and optionally export/render it."""
    payload = load_json_object(arguments.input)
    raw_plan = payload.get("episode_director_plan", payload)
    if not isinstance(raw_plan, dict):
        raise TypeError("Episode input must contain an episode director plan object.")
    plan = EpisodeDirectorPlan.from_dict(raw_plan)
    audio_keys: dict[str, str] = {}
    if arguments.audio_map:
        audio_payload = load_json_object(arguments.audio_map)
        raw_audio = audio_payload.get("audio", audio_payload)
        if not isinstance(raw_audio, dict):
            raise TypeError("Audio map must contain a shot-id to storage-key object.")
        audio_keys = {str(key): str(value) for key, value in raw_audio.items()}

    storage = LocalFsStorage(arguments.storage_root)
    result = awaitable_run(
        EpisodeAnimaticService(storage).build(
            plan,
            dialogue_audio_keys=audio_keys,
            mode=arguments.mode,
        )
    )
    if result.status == "BLOCKED":
        print(write_json(arguments.output, result.to_dict()))
        return 2

    output = result.to_dict()
    if result.project is not None and arguments.export:
        from infrastructure.providers.render.remotion_animatic_exporter import (
            RemotionAnimaticExporter,
        )

        props_path = awaitable_run(
            RemotionAnimaticExporter(
                storage,
                arguments.motion_public_dir,
            ).export(result.project)
        )
        output["remotion_props_path"] = str(props_path)
        if arguments.render:
            from core.application.services.animatic_render_service import (
                AnimaticRenderService,
            )
            from infrastructure.providers.render.ffprobe_media_inspection_provider import (
                FfprobeMediaInspectionProvider,
            )

            render_output = arguments.render_output or str(
                Path(arguments.output).with_suffix(".mp4")
            )
            render_result = awaitable_run(
                AnimaticRenderService(
                    motion_directory="motion",
                    inspector=FfprobeMediaInspectionProvider(),
                ).render(
                    result.project,
                    props_path=props_path,
                    output_path=render_output,
                )
            )
            output["render"] = render_result.to_dict()
            if render_result.status != "READY_FOR_REVIEW":
                print(write_json(arguments.output, output))
                return 3
    elif arguments.render:
        output["render"] = {
            "status": "BLOCKED",
            "error": (
                "MP4 render requires a resolved animatic project; use PLACEHOLDER "
                "mode for a review render."
            ),
        }
        print(write_json(arguments.output, output))
        return 3

    print(write_json(arguments.output, output))
    return 0


__all__ = ["run_episode_animatic_command"]
