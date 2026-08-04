#!/usr/bin/env python3
"""
Sprint 8 manual test entrypoint — Automatic Subtitle Generation.

An eighth composition root, structurally the sibling of
scripts/render_video.py rather than an extension of it: both start from
the same topic -> Script -> VoiceTrack -> ScenePlan prefix, then diverge.
render_video.py continues down the asset-matching/timeline/render branch;
this script stops at ScenePlan and hands it to the new SubtitleService
instead. SubtitleTrack generation has no dependency on AssetMatchPlan,
Timeline, or RenderedVideo -- see SubtitleTrack's own docstring.

  python scripts/generate_subtitles.py "Titanic"

To deliver a subtitle file alongside a specific already-rendered video
(the common case -- see render_video.py's own --subtitle flag for doing
both in one run), pass the RenderedVideo's id so the exported .srt/.vtt
files are saved under the same storage-key prefix RenderService already
used for that video (render/{id}.mp4 -> render/{id}.srt / render/{id}.vtt):

  python scripts/generate_subtitles.py "Titanic" --rendered-video-id <id>

Without --rendered-video-id, a fresh id is generated and files are saved
under subtitles/{id}.srt / subtitles/{id}.vtt. This correlation is a
composition-root-level storage-key naming convention only -- SubtitleTrack
itself never references a RenderedVideo id (see SubtitleTrack's docstring
for why).

This script is the Sprint 8 composition root: the one place that wires
the concrete Claude/ElevenLabs providers and LocalFsStorage together for
the Script -> VoiceTrack -> ScenePlan prefix, then hands the resulting
ScenePlan to the new SubtitleService. SubtitleService itself never knows
Claude or ElevenLabs exist -- it depends only on StoragePort.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.provider_registry import (  # noqa: E402
    get_scene_planning_provider,
    get_voice_provider,
)
from config.settings import get_settings  # noqa: E402
from core.application.services.scene_planning_service import ScenePlanningService  # noqa: E402
from core.application.services.script_service import ScriptService  # noqa: E402
from core.application.services.subtitle_service import SubtitleService  # noqa: E402
from core.application.services.voice_service import VoiceService  # noqa: E402
from core.domain.exceptions import SelmaError  # noqa: E402
from infrastructure.providers.script.claude_script_provider import (  # noqa: E402
    ClaudeScriptProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    """Builds this script's argparse parser without executing anything --
    same extraction scripts/render_video.py uses, so CLI argument behavior
    is unit-testable without invoking any provider or network call. See
    tests/unit/test_generate_subtitles_cli.py."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Script, narration, and Scene Plan for a topic, "
            "then split it into a timed SubtitleTrack exported as "
            ".srt and .vtt files."
        )
    )
    parser.add_argument(
        "topic", type=str,
        help="Topic to generate a script, narration, scene plan, and "
             "subtitle track for.",
    )
    parser.add_argument(
        "--rendered-video-id", type=str, default=None,
        help="If given, exported files are saved as "
             "render/<id>.srt / render/<id>.vtt -- the same storage-key "
             "prefix RenderService uses for render/<id>.mp4, so the "
             "subtitle files sit alongside that rendered video. If "
             "omitted, a fresh id is generated and files are saved under "
             "subtitles/<id>.srt / subtitles/<id>.vtt.",
    )
    parser.add_argument(
        "--max-chars-per-line", type=int, default=None,
        help="Maximum characters per subtitle line. Defaults to 42.",
    )
    parser.add_argument(
        "--max-lines-per-cue", type=int, default=None,
        help="Maximum lines displayed per subtitle cue. Defaults to 2.",
    )
    parser.add_argument(
        "--min-cue-seconds", type=float, default=None,
        help="Minimum on-screen duration per cue, seconds. Defaults to 1.2.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print the SubtitleTrack as JSON instead of the "
             "human-readable summary.",
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

        subtitle_kwargs = {}
        if args.max_chars_per_line is not None:
            subtitle_kwargs["max_chars_per_line"] = args.max_chars_per_line
        if args.max_lines_per_cue is not None:
            subtitle_kwargs["max_lines_per_cue"] = args.max_lines_per_cue
        if args.min_cue_seconds is not None:
            subtitle_kwargs["min_cue_seconds"] = args.min_cue_seconds
        subtitle_service = SubtitleService(storage=storage, **subtitle_kwargs)

        subtitle_track = subtitle_service.generate(scene_plan)

        base_key = (
            f"render/{args.rendered_video_id}"
            if args.rendered_video_id
            else f"subtitles/{uuid.uuid4()}"
        )
        references = await subtitle_service.export(subtitle_track, base_key)
    except SelmaError as exc:
        print(f"Subtitle generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        import json
        print(json.dumps(subtitle_track.to_dict(), indent=2))
        return

    print("=" * 60)
    print(f"Subtitle track:    {subtitle_track.id}")
    print(f"Cues:              {len(subtitle_track.cues)}")
    print(f"Duration:          {subtitle_track.total_duration_seconds:.1f}s")
    print(f"SRT file:          {references['srt'].path}")
    print(f"VTT file:          {references['vtt'].path}")
    print("=" * 60)
    for cue in subtitle_track.cues:
        print(f"[{cue.index}] {cue.start_time:.2f}s \u2013 {cue.end_time:.2f}s (scene {cue.scene_index})")
        print(cue.text)
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
