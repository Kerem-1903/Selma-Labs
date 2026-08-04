#!/usr/bin/env python3
"""
Sprint 1 manual test entrypoint.

Usage:
    python scripts/generate_script_test.py "Why did the Roman Empire collapse?"
    python scripts/generate_script_test.py "The physics of black holes" --duration 60

This is the composition root for Sprint 1: it is the one place that wires
the concrete ClaudeScriptProvider into ScriptService. Every other file in
core/ knows only about ScriptGeneratorPort.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running this script directly (python scripts/generate_script_test.py)
# without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings  # noqa: E402
from core.application.services.script_service import ScriptService  # noqa: E402
from core.domain.exceptions import SelmaError  # noqa: E402
from infrastructure.providers.script.claude_script_provider import (  # noqa: E402
    ClaudeScriptProvider,
)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a SELMA Shorts narration script from a topic."
    )
    parser.add_argument("topic", type=str, help="Topic to generate a script about")
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Target spoken duration in seconds (15-90). Defaults to config value.",
    )
    args = parser.parse_args()

    settings = get_settings()
    duration = args.duration or settings.default_target_duration_seconds

    try:
        provider = ClaudeScriptProvider(
            api_key=settings.anthropic_api_key, model=settings.script_model
        )
        service = ScriptService(provider)
        script = await service.generate(topic=args.topic, target_duration_seconds=duration)
    except SelmaError as exc:
        print(f"Script generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print(f"Topic:            {script.topic}")
    print(f"Target duration:  {script.target_duration_seconds}s")
    print(f"Word count:       {script.estimated_word_count}")
    print(f"Provider:         {script.provider_used}")
    print(f"Script ID:        {script.id}")
    print("=" * 60)
    print(script.full_text)
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
