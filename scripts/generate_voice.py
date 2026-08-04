#!/usr/bin/env python3
"""
Sprint 2 manual test entrypoint — Voice Generation.

Two modes:

  1. Full pipeline (topic -> script via Claude -> narrated audio via ElevenLabs):
     python scripts/generate_voice.py "Titanic"

  2. Voice-only (skip script generation, narrate raw text directly — useful
     for testing voice generation without needing an Anthropic key):
     python scripts/generate_voice.py --text "The Titanic sank in 1912."

This script is the Sprint 2 composition root: the one place that wires
concrete providers (Claude, ElevenLabs) and the concrete storage backend
into the services. VoiceService itself never knows which provider or
storage backend it's using.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.provider_registry import get_voice_provider  # noqa: E402
from config.settings import get_settings  # noqa: E402
from core.application.services.script_service import ScriptService  # noqa: E402
from core.application.services.voice_service import VoiceService  # noqa: E402
from core.domain.entities.script import Script  # noqa: E402
from core.domain.exceptions import SelmaError  # noqa: E402
from infrastructure.providers.script.claude_script_provider import (  # noqa: E402
    ClaudeScriptProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate narrated audio from a topic or raw text."
    )
    parser.add_argument(
        "topic", type=str, nargs="?", default=None,
        help="Topic to generate a script and narration for.",
    )
    parser.add_argument(
        "--text", type=str, default=None,
        help="Narrate this raw text directly, skipping script generation.",
    )
    parser.add_argument(
        "--voice-id", type=str, default=None,
        help="Override the configured ElevenLabs voice id for this run.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print the VoiceTrack as JSON (audio_file, duration, segments) "
             "instead of the human-readable summary.",
    )
    args = parser.parse_args()

    if not args.topic and not args.text:
        parser.error("Provide a topic, or use --text for voice-only testing.")

    settings = get_settings()
    storage = LocalFsStorage(root_dir=settings.storage_root_dir)

    try:
        voice_provider = get_voice_provider(settings)
        voice_service = VoiceService(
            provider=voice_provider,
            storage=storage,
            default_voice_name=settings.elevenlabs_voice_id,
        )

        if args.text:
            script = Script.create(
                topic="(voice-only test)",
                full_text=args.text,
                target_duration_seconds=settings.default_target_duration_seconds,
                provider_used="manual",
            )
        else:
            script_provider = ClaudeScriptProvider(
                api_key=settings.anthropic_api_key, model=settings.script_model
            )
            script_service = ScriptService(script_provider)
            script = await script_service.generate(
                topic=args.topic,
                target_duration_seconds=settings.default_target_duration_seconds,
            )
            print(f"Script generated ({script.estimated_word_count} words). Narrating...\n")

        voice_track = await voice_service.generate(script=script, voice_name=args.voice_id)
    except SelmaError as exc:
        print(f"Voice generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        import json
        print(json.dumps(voice_track.to_dict(), indent=2))
        return

    print("=" * 60)
    print(f"Audio ID:      {voice_track.audio_id}")
    print(f"Duration:      {voice_track.duration_seconds:.1f}s")
    print(f"Provider:      {voice_track.provider}")
    print(f"Voice used:    {voice_track.voice_name}")
    print(f"Sample rate:   {voice_track.sample_rate} Hz")
    print(f"File path:     {voice_track.file_path}")
    if voice_track.segments:
        print(f"Segments:      {len(voice_track.segments)} timed segments available")
    else:
        print("Segments:      none (provider did not supply timing data)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
