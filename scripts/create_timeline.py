#!/usr/bin/env python3
"""
Sprint 6 manual test entrypoint — Timeline Creation.

Two modes:

  1. Full pipeline (topic -> Claude script -> ElevenLabs voice -> Claude
     scene plan -> Pexels-matched candidates per scene -> downloaded
     Timeline):
     python scripts/create_timeline.py "Titanic"

  2. Narration-only (skip script + voice generation, plan scenes and build
     a Timeline directly from raw text with an estimated duration --
     useful for testing with only Anthropic + Pexels keys, no ElevenLabs
     key or quota needed):
     python scripts/create_timeline.py --text "The Titanic left Southampton in 1912."
     python scripts/create_timeline.py --text "..." --duration 30

This script is the Sprint 6 composition root: the one place that wires the
concrete Claude/ElevenLabs/Pexels providers and LocalFsStorage into
ScriptService, VoiceService, ScenePlanningService, VideoSearchService,
SceneAssetMatchingService, and TimelineService. TimelineService itself
never knows which provider is behind the VideoSearchService it's handed --
it depends on VideoSearchService directly (a sibling application service,
not a Port -- see that module's docstring for why), and VideoSearchService
in turn depends only on VideoSourcePort/StoragePort.

Video rendering (turning this Timeline into an actual video file) is out
of scope for this script and this sprint -- see Sprint 7.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.provider_registry import (  # noqa: E402
    get_scene_planning_provider,
    get_video_source_provider,
    get_voice_provider,
)
from config.settings import get_settings  # noqa: E402
from core.application.services.scene_asset_matching_service import (  # noqa: E402
    DEFAULT_CANDIDATES_PER_SCENE,
    SceneAssetMatchingService,
)
from core.application.services.scene_planning_service import ScenePlanningService  # noqa: E402
from core.application.services.script_service import ScriptService  # noqa: E402
from core.application.services.timeline_service import TimelineService  # noqa: E402
from core.application.services.video_search_service import VideoSearchService  # noqa: E402
from core.application.services.voice_service import VoiceService  # noqa: E402
from core.domain.entities.script import Script  # noqa: E402
from core.domain.entities.voice_track import VoiceTrack  # noqa: E402
from core.domain.exceptions import SelmaError  # noqa: E402
from infrastructure.providers.script.claude_script_provider import (  # noqa: E402
    ClaudeScriptProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage  # noqa: E402

# Only used to estimate a duration in --text mode when --duration isn't
# given; ScriptService uses the same figure for its own sanity bound.
WORDS_PER_MINUTE_ESTIMATE = 150


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a downloadable Timeline (one selected asset per scene) "
            "from a topic or directly from raw narration text."
        )
    )
    parser.add_argument(
        "topic", type=str, nargs="?", default=None,
        help="Topic to generate a script, narration, scene plan, asset "
             "matches, and Timeline for.",
    )
    parser.add_argument(
        "--text", type=str, default=None,
        help="Plan scenes and build a Timeline for this raw narration "
             "text directly, skipping script and voice generation.",
    )
    parser.add_argument(
        "--duration", type=float, default=None,
        help="Total narration duration in seconds, used only with --text "
             "(estimated from word count if omitted).",
    )
    parser.add_argument(
        "--candidates-per-scene", type=int, default=None,
        help=f"Maximum candidate assets to consider per scene before "
             f"ranking. Defaults to {DEFAULT_CANDIDATES_PER_SCENE}.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print the Timeline as JSON instead of the human-readable "
             "summary.",
    )
    args = parser.parse_args()

    if not args.topic and not args.text:
        parser.error("Provide a topic, or --text for narration-only mode.")

    settings = get_settings()

    try:
        if args.text:
            estimated_duration = args.duration or (
                len(args.text.split()) / WORDS_PER_MINUTE_ESTIMATE * 60
            )
            script = Script.create(
                topic="(manual narration)",
                full_text=args.text,
                target_duration_seconds=int(args.duration or 45),
                provider_used="manual",
            )
            voice_track = VoiceTrack.create(
                script_id=script.id,
                duration_seconds=estimated_duration,
                provider="estimated",
                voice_name="none",
                sample_rate=0,
                file_path="",
            )
        else:
            script_provider = ClaudeScriptProvider(
                api_key=settings.anthropic_api_key, model=settings.script_model
            )
            script = await ScriptService(script_provider).generate(
                topic=args.topic,
                target_duration_seconds=settings.default_target_duration_seconds,
            )

            voice_service = VoiceService(
                provider=get_voice_provider(settings),
                storage=LocalFsStorage(root_dir=settings.storage_root_dir),
                default_voice_name=settings.elevenlabs_voice_id,
            )
            voice_track = await voice_service.generate(script)

        scene_service = ScenePlanningService(provider=get_scene_planning_provider(settings))
        scene_plan = await scene_service.plan(script=script, voice_track=voice_track)

        video_search_service = VideoSearchService(
            provider=get_video_source_provider(settings),
            storage=LocalFsStorage(root_dir=settings.storage_root_dir),
        )
        matching_kwargs = {}
        if args.candidates_per_scene is not None:
            matching_kwargs["candidates_per_scene"] = args.candidates_per_scene
        matching_service = SceneAssetMatchingService(video_search_service, **matching_kwargs)
        asset_match_plan = await matching_service.match(scene_plan)

        timeline_service = TimelineService(video_search_service)
        timeline = await timeline_service.create(asset_match_plan)
    except SelmaError as exc:
        print(f"Timeline creation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        import json
        print(json.dumps(timeline.to_dict(), indent=2))
        return

    print("=" * 60)
    print(f"Timeline:          {timeline.id}")
    print(f"Clips:             {len(timeline.clips)}")
    print(f"Total duration:    {timeline.total_duration_seconds:.1f}s")
    print("=" * 60)
    for clip in timeline.clips:
        scene = clip.scene
        print(f"Scene {scene.index + 1}  [{scene.start_time:.1f}s - {scene.end_time:.1f}s]")
        print(f"Narration: {scene.narration}")
        print(f"Asset:     {clip.asset.id}  ({clip.asset.local_path})")
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
