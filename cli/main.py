from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from config.container import AnimationContainer, create_container
from core.application.services.script_breakdown_service import ScriptBreakdownService
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.shot_animation import ShotPlan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SELMA Labs anime production CLI")
    commands = parser.add_subparsers(dest="command", required=True)

    character = commands.add_parser("character", help="Inspect canonical characters")
    character_commands = character.add_subparsers(dest="character_command", required=True)
    character_commands.add_parser("show", help="Show the canonical Akira Character Bible")

    script = commands.add_parser("script", help="Break a script into executable shots")
    script_commands = script.add_subparsers(dest="script_command", required=True)
    breakdown = script_commands.add_parser("breakdown")
    breakdown.add_argument("--input", required=True, help="UTF-8 text script")
    breakdown.add_argument("--script-id", default="akira-pilot")
    breakdown.add_argument("--output", help="Optional JSON output file")

    render = commands.add_parser("render", help="Render approved anime shots")
    render_commands = render.add_subparsers(dest="render_command", required=True)
    shot = render_commands.add_parser("shot")
    shot.add_argument("--plan", required=True, help="Shot JSON or breakdown JSON")
    shot.add_argument("--shot-id", help="Required when --plan contains multiple shots")
    shot.add_argument("--background-key", required=True)
    shot.add_argument("--audio-key", required=True)
    shot.add_argument("--output-key", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    container_factory: Callable[[], AnimationContainer] = create_container,
) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "character":
            _show_character(CharacterBible.akira())
        elif arguments.command == "script":
            _break_down_script(arguments)
        elif arguments.command == "render":
            asyncio.run(_render_shot(arguments, container_factory()))
        return 0
    except Exception as error:  # noqa: BLE001 - CLI boundary
        print(f"SELMA command failed: {error}", file=sys.stderr)
        return 1


def _show_character(bible: CharacterBible) -> None:
    payload = bible.to_dict()
    payload["prompt_fragments"] = list(bible.prompt_fragments())
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _break_down_script(arguments: argparse.Namespace) -> None:
    source = Path(arguments.input)
    script_text = source.read_text(encoding="utf-8")
    service = ScriptBreakdownService(CharacterBible.akira())
    shots = service.parse_script(script_text, script_id=arguments.script_id)
    payload = {
        "schema_version": 1,
        "script_id": arguments.script_id,
        "shots": [shot.to_dict() for shot in shots],
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if arguments.output:
        output = Path(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{serialized}\n", encoding="utf-8")
        print(str(output.resolve()))
    else:
        print(serialized)


async def _render_shot(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> None:
    payload = json.loads(Path(arguments.plan).read_text(encoding="utf-8"))
    shot_payload = _select_shot_payload(payload, arguments.shot_id)
    shot = ShotPlan.from_dict(shot_payload)
    output = await container.animation_orchestrator_service.orchestrate_shot(
        shot_plan=shot,
        background_image_path=arguments.background_key,
        audio_path=arguments.audio_key,
        output_path=arguments.output_key,
    )
    print(output)


def _select_shot_payload(payload: Any, shot_id: str | None) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("shots"), list):
        shots = [item for item in payload["shots"] if isinstance(item, dict)]
        if not shot_id:
            raise ValueError("--shot-id is required for a breakdown containing multiple shots.")
        matches = [item for item in shots if str(item.get("id")) == shot_id]
        if len(matches) != 1:
            raise ValueError(f"Shot '{shot_id}' was not found exactly once in the plan.")
        return matches[0]
    if not isinstance(payload, dict):
        raise TypeError("Shot plan JSON must contain an object.")
    if shot_id and str(payload.get("id")) != shot_id:
        raise ValueError(f"Shot plan does not contain requested shot '{shot_id}'.")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
