#!/usr/bin/env python3
"""
Sprint 5 manual test entrypoint — Scene Asset Matching.

Two modes:

  1. Full pipeline (topic -> Claude script -> ElevenLabs voice -> Claude
     scene plan -> Pexels-matched candidates per scene):
     python scripts/match_assets.py "Titanic"

  2. Narration-only (skip script + voice generation, plan scenes and match
     assets directly from raw text with an estimated duration -- useful
     for testing with only Anthropic + Pexels keys, no ElevenLabs key or
     quota needed):
     python scripts/match_assets.py --text "The Titanic left Southampton in 1912."
     python scripts/match_assets.py --text "..." --duration 30

This script is the Sprint 5 composition root: the one place that wires the
concrete Claude/ElevenLabs/Pexels providers and LocalFsStorage into
ScriptService, VoiceService, ScenePlanningService, VideoSearchService, and
SceneAssetMatchingService. SceneAssetMatchingService itself never knows
which provider is behind the VideoSearchService it's handed -- it depends
on VideoSearchService directly (a sibling application service, not a
Port -- see that module's docstring for why), and VideoSearchService in
turn depends only on VideoSourcePort/StoragePort.
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
            "Match visual asset candidates to each scene of a Scene Plan, "
            "from a topic or directly from raw narration text."
        )
    )
    parser.add_argument(
        "topic", type=str, nargs="?", default=None,
        help="Topic to generate a script, narration, scene plan, and asset "
             "matches for.",
    )
    parser.add_argument(
        "--text", type=str, default=None,
        help="Plan scenes and match assets for this raw narration text "
             "directly, skipping script and voice generation.",
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
        help="Print the AssetMatchPlan as JSON instead of the "
             "human-readable summary.",
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
    except SelmaError as exc:
        print(f"Scene asset matching failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        import json
        print(json.dumps(asset_match_plan.to_dict(), indent=2))
        return

    matched_count = sum(1 for m in asset_match_plan.matches if m.has_matches)
    print("=" * 60)
    print(f"Scenes:          {len(asset_match_plan.matches)}")
    print(f"Matched scenes:  {matched_count}")
    print(f"Unmatched scenes: {len(asset_match_plan.matches) - matched_count}")
    print("=" * 60)
    for match in asset_match_plan.matches:
        scene = match.scene
        print(f"Scene {scene.index + 1}")
        print(f"Narration: {scene.narration}")
        print(f"Keywords:  {', '.join(scene.search_keywords)}")
        if not match.has_matches:
            print("Assets:    (none found)")
        else:
            print(f"Assets:    {len(match.assets)} candidate(s), best first")
            for rank, asset in enumerate(match.assets, start=1):
                print(
                    f"  {rank}. {asset.id}  {asset.width}x{asset.height}  "
                    f"{asset.duration_seconds}s  tags={asset.tags}"
                )
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
