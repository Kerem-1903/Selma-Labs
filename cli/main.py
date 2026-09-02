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
from core.domain.entities.episode_script import EpisodeScript
from core.domain.entities.shot_animation import ShotPlan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SELMA Labs anime production CLI")
    commands = parser.add_subparsers(dest="command", required=True)

    character = commands.add_parser("character", help="Inspect canonical characters")
    character_commands = character.add_subparsers(
        dest="character_command", required=True
    )
    character_commands.add_parser(
        "show", help="Show the canonical Akira Character Bible"
    )

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

    blender = commands.add_parser("blender", help="Blender Integration and A8.2 tools")
    blender_commands = blender.add_subparsers(dest="blender_command", required=True)

    register = blender_commands.add_parser("register-views")
    register.add_argument(
        "--input", required=True, help="Path to multiview reference image"
    )

    turntable = blender_commands.add_parser("turntable")
    turntable.add_argument("--model", required=True, help="Path to 3D model")
    turntable.add_argument(
        "--output-dir", default="output/blender", help="Directory for output"
    )
    turntable.add_argument(
        "--quality", default="preview", help="Render quality (preview, high)"
    )

    benchmark = blender_commands.add_parser("benchmark")
    benchmark.add_argument("--model", required=True, help="Path to 3D model")

    rig = commands.add_parser("rig", help="A9 Rig and Acting Validation Tools")
    rig_commands = rig.add_subparsers(dest="rig_command", required=True)

    validate = rig_commands.add_parser("validate")
    validate.add_argument("--model", required=True, help="Path to blender model")

    preview = rig_commands.add_parser("preview")
    preview.add_argument("--model", required=True, help="Path to blender model")
    preview.add_argument("--action", required=True, help="Action name to preview")
    preview.add_argument(
        "--output", default="output/blender/preview.mp4", help="Output video path"
    )

    preproduction = commands.add_parser(
        "preproduction", help="Run the locked P1-P8 anime pre-production workflow"
    )
    preproduction_commands = preproduction.add_subparsers(
        dest="preproduction_command", required=True
    )
    preproduction_commands.add_parser("status", help="Validate active canon locks")
    golden_set = preproduction_commands.add_parser(
        "golden-set", help="Generate Akira's ten-image consistency set"
    )
    golden_set.add_argument("--model-id", required=True)
    golden_set.add_argument("--model-revision", required=True)
    golden_set.add_argument(
        "--output", default="output/preproduction/akira-golden-set.json"
    )
    production_plan = preproduction_commands.add_parser(
        "plan", help="Convert an approved EpisodeScript JSON into a shot hierarchy"
    )
    production_plan.add_argument("--input", required=True)
    production_plan.add_argument("--output", required=True)

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
        elif arguments.command == "blender":
            asyncio.run(_run_blender_commands(arguments, container_factory()))
        elif arguments.command == "rig":
            return asyncio.run(_run_rig_commands(arguments))
        elif arguments.command == "preproduction":
            return asyncio.run(
                _run_preproduction_commands(arguments, container_factory())
            )
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


async def _run_blender_commands(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> None:
    if arguments.blender_command == "register-views":
        from core.application.services.multiview_asset_registration_service import (
            MultiviewAssetRegistrationService,
        )

        service = MultiviewAssetRegistrationService(container.storage)
        updated_bible = await service.register_multiview_asset(
            bible=container.character_bible, image_path=arguments.input
        )
        print("Successfully registered multiview assets.")
        _show_character(updated_bible)
    elif arguments.blender_command == "turntable":
        from config.settings import get_settings
        from infrastructure.providers.blender.blender_scene_adapter import (
            BlenderSceneAdapter,
        )

        adapter = BlenderSceneAdapter(blender_bin_path=get_settings().blender_bin_path)
        manifest = await adapter.render_turntable(
            model_path=arguments.model,
            output_dir=arguments.output_dir,
            resolution_profile=arguments.quality,
        )
        print(json.dumps(manifest.to_dict(), indent=2))
    elif arguments.blender_command == "benchmark":
        from config.settings import get_settings
        from infrastructure.providers.blender.blender_scene_adapter import (
            BlenderSceneAdapter,
        )

        adapter = BlenderSceneAdapter(blender_bin_path=get_settings().blender_bin_path)
        stats = await adapter.run_benchmark(model_path=arguments.model)
        print(json.dumps(stats, indent=2))


async def _run_rig_commands(arguments: argparse.Namespace) -> int:
    from dataclasses import asdict

    from config.settings import get_settings
    from core.application.services.rig_validation_service import RigValidationService
    from core.domain.exceptions import RigValidationError
    from infrastructure.providers.blender.blender_rig_adapter import BlenderRigAdapter

    adapter = BlenderRigAdapter(blender_bin_path=get_settings().blender_bin_path)
    service = RigValidationService(adapter)

    if arguments.rig_command == "validate":
        report = await service.validate_character_rig(arguments.model)

        # Convert frozensets to lists for JSON serialization
        spec_dict = asdict(report.specification)
        spec_dict["shape_keys"] = sorted(spec_dict["shape_keys"])
        spec_dict["available_actions"] = sorted(spec_dict["available_actions"])

        output = {
            "is_valid": report.is_valid,
            "errors": report.errors,
            "specification": spec_dict,
        }
        print(json.dumps(output, indent=2))
        return 0 if report.is_valid else 2
    elif arguments.rig_command == "preview":
        report = await service.validate_character_rig(arguments.model)
        if not report.is_valid:
            raise RigValidationError(" ".join(report.errors))
        output_path = await adapter.bake_action_preview(
            model_path=arguments.model,
            action_name=arguments.action,
            output_path=arguments.output,
        )
        print(f"Preview saved to: {output_path}")
        return 0
    raise ValueError(f"Unsupported rig command: {arguments.rig_command}")


async def _run_preproduction_commands(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> int:
    if arguments.preproduction_command == "status":
        direction = await container.canon_repository.get_creative_direction()
        world = await container.canon_repository.get_world_bible()
        visual = await container.canon_repository.get_visual_style()
        characters = await container.canon_repository.get_character_bibles()
        payload = {
            "schema_version": 1,
            "story_canon_locked": direction.status.value == "LOCKED",
            "world_canon_locked": world.status.value == "LOCKED",
            "visual_style_locked": visual.status.value == "LOCKED",
            "characters": [
                {
                    "character_id": bible.character_id,
                    "narrative_locked": bool(
                        bible.narrative_profile and bible.narrative_profile.locked
                    ),
                    "reference_count": len(bible.reference_pack),
                }
                for bible in characters
            ],
            "next_gate": "GOLDEN_SET",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if arguments.preproduction_command == "plan":
        source = json.loads(Path(arguments.input).read_text(encoding="utf-8"))
        script_payload = source.get("episode_script", source)
        script = EpisodeScript.from_dict(dict(script_payload))
        plan = container.hierarchical_shot_planning_service.plan(script)
        target = Path(arguments.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"schema_version": 1, "episode_production_plan": plan.to_dict()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(str(target.resolve()))
        return 0
    if arguments.preproduction_command == "golden-set":
        visual = await container.canon_repository.get_visual_style()
        characters = await container.canon_repository.get_character_bibles()
        matches = [item for item in characters if item.character_id == "akira"]
        if len(matches) != 1:
            raise ValueError("The locked Akira Character Bible was not found exactly once.")
        golden_set = await container.character_golden_set_service.run(
            character=matches[0],
            style=visual,
            model_id=arguments.model_id,
            model_revision=arguments.model_revision,
        )
        target = Path(arguments.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"schema_version": 1, "golden_set": golden_set.to_dict()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(str(target.resolve()))
        return 0
    raise ValueError(
        f"Unsupported preproduction command: {arguments.preproduction_command}"
    )


def _select_shot_payload(payload: Any, shot_id: str | None) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("shots"), list):
        shots = [item for item in payload["shots"] if isinstance(item, dict)]
        if not shot_id:
            raise ValueError(
                "--shot-id is required for a breakdown containing multiple shots."
            )
        matches = [item for item in shots if str(item.get("id")) == shot_id]
        if len(matches) != 1:
            raise ValueError(
                f"Shot '{shot_id}' was not found exactly once in the plan."
            )
        return matches[0]
    if not isinstance(payload, dict):
        raise TypeError("Shot plan JSON must contain an object.")
    if shot_id and str(payload.get("id")) != shot_id:
        raise ValueError(f"Shot plan does not contain requested shot '{shot_id}'.")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
