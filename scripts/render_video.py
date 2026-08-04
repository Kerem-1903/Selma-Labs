#!/usr/bin/env python3
"""
Sprint 7 manual test entrypoint — Video Rendering.

Extends scripts/create_timeline.py one stage further: after building a
Timeline exactly as that script does, hands it (plus the VoiceTrack's
``file_path``, extracted here at the composition root rather than passed
into RenderService as a whole VoiceTrack -- see RenderPort's docstring for
why) to the new RenderService.

  python scripts/render_video.py "Titanic"

``--text`` mode (skip script + voice generation) is intentionally NOT
supported here, unlike scripts/create_timeline.py: that mode builds a
VoiceTrack with ``file_path=""`` (no real audio was ever generated, only an
estimated duration), so there is nothing for RenderService to mux. Video
rendering needs a real narration audio file to exist on disk -- if you only
have raw text, run the full pipeline (this script always generates real
narration audio via ElevenLabs).

This script is the Sprint 7 composition root: the one place that wires the
concrete Claude/ElevenLabs/Pexels/FFmpeg providers and LocalFsStorage
together, exactly as scripts/create_timeline.py does one stage earlier,
extended with RenderService/RenderPort. RenderService itself never knows
FFmpeg is behind the RenderPort it's handed -- it depends only on
RenderPort/StoragePort.

Sprint 8 addition -- ``--subtitle``: after rendering completes, optionally
also generates and exports a SubtitleTrack from the same ScenePlan this
run already built, saved as ``render/<rendered_video_id>.srt`` /
``render/<rendered_video_id>.vtt`` alongside ``render/<rendered_video_id>.mp4``.
This is a thin, additive convenience for running both in one pass --
RenderService/RenderPort/Timeline/RenderedVideo are all completely
untouched by it (Sprint 8's own scope explicitly excludes modifying any
of them). Subtitle generation can equally be run on its own, independent
of rendering entirely, via scripts/generate_subtitles.py.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.provider_registry import (  # noqa: E402
    get_render_provider,
    get_scene_planning_provider,
    get_video_source_provider,
    get_voice_provider,
)
from config.settings import get_settings  # noqa: E402
from core.application.services.render_service import RenderService  # noqa: E402
from core.application.services.scene_asset_matching_service import (  # noqa: E402
    DEFAULT_CANDIDATES_PER_SCENE,
    SceneAssetMatchingService,
)
from core.application.services.scene_planning_service import ScenePlanningService  # noqa: E402
from core.application.services.script_service import ScriptService  # noqa: E402
from core.application.services.subtitle_service import SubtitleService  # noqa: E402
from core.application.services.timeline_service import TimelineService  # noqa: E402
from core.application.services.video_search_service import VideoSearchService  # noqa: E402
from core.application.services.voice_service import VoiceService  # noqa: E402
from core.domain.exceptions import SelmaError  # noqa: E402
from infrastructure.providers.script.claude_script_provider import (  # noqa: E402
    ClaudeScriptProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    """Builds this script's argparse parser without executing anything --
    extracted from ``main()`` so CLI argument behavior (topic required,
    ``--subtitle`` defaults to False, ``--candidates-per-scene`` defaults
    to None, etc.) is unit-testable without invoking any provider or
    network call. See tests/unit/test_render_video_cli.py."""
    parser = argparse.ArgumentParser(
        description=(
            "Build a Timeline from a topic and render it, with narration "
            "audio muxed in, into a final MP4 file."
        )
    )
    parser.add_argument(
        "topic", type=str,
        help="Topic to generate a script, narration, scene plan, asset "
             "matches, Timeline, and rendered video for.",
    )
    parser.add_argument(
        "--candidates-per-scene", type=int, default=None,
        help=f"Maximum candidate assets to consider per scene before "
             f"ranking. Defaults to {DEFAULT_CANDIDATES_PER_SCENE}.",
    )
    parser.add_argument(
        "--subtitle", action="store_true",
        help="After rendering, also generate a SubtitleTrack from this "
             "run's ScenePlan and export it as render/<id>.srt / "
             "render/<id>.vtt alongside render/<id>.mp4. Does not burn "
             "subtitles into the video -- sidecar files only.",
    )
    return parser


async def main() -> None:
    args = build_arg_parser().parse_args()

    settings = get_settings()

    try:
        script_provider = ClaudeScriptProvider(
            api_key=settings.anthropic_api_key, model=settings.script_model
        )
        script = await ScriptService(script_provider).generate(
            topic=args.topic,
            target_duration_seconds=settings.default_target_duration_seconds,
        )

        storage = LocalFsStorage(root_dir=settings.storage_root_dir)

        voice_service = VoiceService(
            provider=get_voice_provider(settings),
            storage=storage,
            default_voice_name=settings.elevenlabs_voice_id,
        )
        voice_track = await voice_service.generate(script)

        scene_service = ScenePlanningService(provider=get_scene_planning_provider(settings))
        scene_plan = await scene_service.plan(script=script, voice_track=voice_track)

        video_search_service = VideoSearchService(
            provider=get_video_source_provider(settings), storage=storage
        )
        matching_kwargs = {}
        if args.candidates_per_scene is not None:
            matching_kwargs["candidates_per_scene"] = args.candidates_per_scene
        matching_service = SceneAssetMatchingService(video_search_service, **matching_kwargs)
        asset_match_plan = await matching_service.match(scene_plan)

        timeline_service = TimelineService(video_search_service)
        timeline = await timeline_service.create(asset_match_plan)

        render_service = RenderService(
            render_port=get_render_provider(settings), storage=storage
        )
        # Only VoiceTrack.file_path is extracted here -- RenderService and
        # RenderPort never see the VoiceTrack entity itself.
        rendered_video = await render_service.render(timeline, voice_track.file_path)

        subtitle_references = None
        if args.subtitle:
            # Reuses this run's own ScenePlan -- SubtitleService never
            # touches Timeline/RenderedVideo/RenderPort. The storage-key
            # prefix is chosen here, at the composition root, to
            # correlate with rendered_video.id; SubtitleTrack itself has
            # no field for that id (see SubtitleTrack's docstring).
            subtitle_service = SubtitleService(storage=storage)
            subtitle_track = subtitle_service.generate(scene_plan)
            subtitle_references = await subtitle_service.export(
                subtitle_track, base_key=f"render/{rendered_video.id}"
            )
    except SelmaError as exc:
        print(f"Rendering failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print(f"Rendered video:    {rendered_video.id}")
    print(f"File:              {rendered_video.video_path}")
    print(f"Duration:          {rendered_video.duration_seconds:.1f}s")
    print(f"Resolution:        {rendered_video.width}x{rendered_video.height} @ {rendered_video.fps:.1f}fps")
    if subtitle_references is not None:
        print(f"Subtitles (SRT):   {subtitle_references['srt'].path}")
        print(f"Subtitles (VTT):   {subtitle_references['vtt'].path}")
    print(f"Size:              {rendered_video.size_bytes / 1_000_000:.2f} MB")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
