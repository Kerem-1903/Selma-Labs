#!/usr/bin/env python3
"""
Sprint 4 manual test entrypoint — Scene Planning.

Two modes:

  1. Full pipeline (topic -> Claude script -> ElevenLabs voice -> Claude
     scene plan):
     python scripts/plan_scenes.py "Titanic"

  2. Narration-only (skip script + voice generation, plan scenes directly
     from raw text with an estimated duration -- useful for testing scene
     planning with only an Anthropic key, no ElevenLabs key or quota
     needed):
     python scripts/plan_scenes.py --text "The Titanic left Southampton in 1912."
     python scripts/plan_scenes.py --text "..." --duration 30

This script is the Sprint 4 composition root: the one place that wires the
concrete Claude-based script/scene-planning providers and (in full-pipeline
mode) the voice provider into ScriptService, VoiceService, and
ScenePlanningService. ScenePlanningService itself never knows which
provider produced the Script or VoiceTrack it's handed, nor which provider
is planning the scenes.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.provider_registry import (  # noqa: E402
    get_scene_planning_provider,
    get_voice_provider,
)
from config.settings import get_settings  # noqa: E402
from core.application.services.scene_planning_service import ScenePlanningService  # noqa: E402
from core.application.services.script_service import ScriptService  # noqa: E402
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


def _format_timestamp(seconds: float) -> str:
    total_seconds = max(int(round(seconds)), 0)
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Scene Plan from a topic, or directly from raw narration text."
    )
    parser.add_argument(
        "topic", type=str, nargs="?", default=None,
        help="Topic to generate a script, narration, and scene plan for.",
    )
    parser.add_argument(
        "--text", type=str, default=None,
        help="Plan scenes for this raw narration text directly, skipping "
             "script and voice generation.",
    )
    parser.add_argument(
        "--duration", type=float, default=None,
        help="Total narration duration in seconds, used only with --text "
             "(estimated from word count if omitted).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print the ScenePlan as JSON instead of the human-readable summary.",
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
    except SelmaError as exc:
        print(f"Scene planning failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        import json
        print(json.dumps(scene_plan.to_dict(), indent=2))
        return

    print("=" * 60)
    print(f"Total duration: {scene_plan.total_duration_seconds:.1f}s")
    print(f"Scenes:         {len(scene_plan.scenes)}")
    print("=" * 60)
    for scene in scene_plan.scenes:
        print(f"Scene {scene.index + 1}")
        print(f"{_format_timestamp(scene.start_time)}\u2013{_format_timestamp(scene.end_time)}")
        print(f"Narration: {scene.narration}")
        print("Keywords:")
        for keyword in scene.search_keywords:
            print(f"  {keyword}")
        if scene.detected_objects:
            print("Objects:")
            for obj in scene.detected_objects:
                print(f"  {obj}")
        if scene.location:
            print(f"Location: {scene.location}")
        if scene.mood:
            print(f"Mood: {scene.mood}")
        print(f"Visual priority: {scene.visual_priority}")
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
