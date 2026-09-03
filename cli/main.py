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
    character_show = character_commands.add_parser(
        "show", help="Show a Character Bible (defaults to canonical Akira)"
    )
    character_show.add_argument("--input", help="Optional Character Bible JSON")
    character_init = character_commands.add_parser(
        "init", help="Create a Character Bible from a descriptive brief"
    )
    character_init.add_argument("--brief", required=True)
    character_init.add_argument("--output", required=True)
    character_plan = character_commands.add_parser(
        "plan", help="Create a reusable 20+3 character reference recipe"
    )
    character_plan.add_argument("--input", required=True, help="Character Bible JSON")
    character_plan.add_argument("--output", required=True, help="Onboarding plan JSON")
    character_anchor = character_commands.add_parser(
        "anchor", help="Generate one unapproved identity anchor"
    )
    character_anchor.add_argument("--input", required=True, help="Character Bible JSON")
    character_anchor.add_argument("--output-prefix", default="character-candidates")
    character_anchor.add_argument(
        "--count", type=int, default=3, help="Number of unapproved anchor candidates"
    )
    character_anchor.add_argument(
        "--source-reference-key",
        help="Optional storage key used to bootstrap a reference-locked anchor",
    )
    character_references = character_commands.add_parser(
        "references", help="Generate the 20+3 candidate pack from an approved anchor"
    )
    character_references.add_argument(
        "--input", required=True, help="Character Bible JSON"
    )
    character_references.add_argument("--approved-anchor-key", required=True)
    character_references.add_argument("--output-prefix", default="character-candidates")
    character_references.add_argument("--manifest", required=True)
    character_references.add_argument(
        "--limit", type=int, help="Generate only the first N recipes for a pilot run"
    )
    character_references.add_argument(
        "--defer-visual-review",
        action="store_true",
        help="Keep candidates pending when no trustworthy vision model is available",
    )
    character_references.add_argument(
        "--pilot-approval",
        help="Human pilot-approval receipt required for more than one recipe",
    )
    character_pilot_approve = character_commands.add_parser(
        "approve-pilot", help="Approve the identity/framing pilot after visual review"
    )
    character_pilot_approve.add_argument("--input", required=True)
    character_pilot_approve.add_argument("--approved-anchor-key", required=True)
    character_pilot_approve.add_argument("--pilot-key", required=True)
    character_pilot_approve.add_argument("--approved-by", required=True)
    character_pilot_approve.add_argument("--output", required=True)
    for check in (
        "face-match",
        "hair-match",
        "immutable-marks-match",
        "outfit-match",
        "framing-match",
        "anatomy-pass",
    ):
        character_pilot_approve.add_argument(f"--{check}", action="store_true")
    character_approve = character_commands.add_parser(
        "approve-references",
        help="Register human-selected reference candidates in a Character Bible",
    )
    character_approve.add_argument(
        "--input", required=True, help="Character Bible JSON"
    )
    character_approve.add_argument("--selections", required=True)
    character_approve.add_argument("--approved-by", required=True)
    character_approve.add_argument("--output", required=True)
    character_approve.add_argument(
        "--lock-narrative",
        action="store_true",
        help="Also confirm and lock the narrative profile",
    )
    character_dataset = character_commands.add_parser(
        "dataset", help="Build a LoRA dataset with character-specific captions"
    )
    character_dataset.add_argument(
        "--input", required=True, help="Character Bible JSON"
    )
    character_dataset.add_argument("--source", required=True)
    character_dataset.add_argument("--output", required=True)
    character_dataset.add_argument(
        "--trigger-token",
        help="Defaults to the character-specific schema-v2 trigger token",
    )
    character_dataset.add_argument(
        "--review-manifest", help="Human review JSON for every source image"
    )
    character_dataset.add_argument(
        "--canonical-anchor", help="Approved identity anchor used to verify lineage"
    )
    character_audit = character_commands.add_parser(
        "audit-dataset", help="Audit an existing LoRA dataset without training"
    )
    character_audit.add_argument("--manifest", required=True)
    character_audit.add_argument("--output")
    character_review_template = character_commands.add_parser(
        "review-template", help="Create a fail-closed per-image review form"
    )
    character_review_template.add_argument("--manifest", required=True)
    character_review_template.add_argument("--canonical-anchor", required=True)
    character_review_template.add_argument("--output", required=True)
    character_train = character_commands.add_parser(
        "train", help="Train a validated character LoRA with the 8 GB profile"
    )
    character_train.add_argument("--input", required=True, help="Character Bible JSON")
    character_train.add_argument("--dataset", required=True)
    character_train.add_argument("--base-model", required=True)
    character_train.add_argument("--sd-scripts-dir", required=True)
    character_train.add_argument("--output", required=True)
    character_train.add_argument("--model-name", required=True)
    character_train.add_argument("--steps", type=int, default=240)

    background = commands.add_parser(
        "background", help="Create consistent, character-free anime locations"
    )
    background_commands = background.add_subparsers(
        dest="background_command", required=True
    )
    background_init = background_commands.add_parser(
        "init", help="Create a Location Bible from a descriptive brief"
    )
    background_init.add_argument("--brief", required=True)
    background_init.add_argument("--output", required=True)
    background_plan = background_commands.add_parser(
        "plan", help="Create the reusable 12-shot coverage plan"
    )
    background_plan.add_argument("--input", required=True)
    background_plan.add_argument("--output", required=True)
    background_generate = background_commands.add_parser(
        "generate", help="Generate automatically reviewed clean background plates"
    )
    background_generate.add_argument("--input", required=True)
    background_generate.add_argument("--output-prefix", default="background-candidates")
    background_generate.add_argument("--manifest", required=True)
    background_approve = background_commands.add_parser(
        "approve", help="Human-approve a complete background pack and lock the location"
    )
    background_approve.add_argument("--input", required=True)
    background_approve.add_argument("--manifest", required=True)
    background_approve.add_argument("--approved-by", required=True)
    background_approve.add_argument("--output", required=True)

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
        "golden-set", help="Generate a character's ten-image consistency set"
    )
    golden_set.add_argument("--character-id", default="akira")
    golden_set.add_argument("--model-id", required=True)
    golden_set.add_argument("--model-revision", required=True)
    golden_set.add_argument(
        "--output", help="Defaults to output/preproduction/<character>-golden-set.json"
    )
    production_plan = preproduction_commands.add_parser(
        "plan", help="Convert an approved EpisodeScript JSON into a shot hierarchy"
    )
    production_plan.add_argument("--input", required=True)
    production_plan.add_argument("--output", required=True)

    keyframe = commands.add_parser("keyframe", help="Keyframe generation tools")
    keyframe_commands = keyframe.add_subparsers(dest="keyframe_command", required=True)
    pair = keyframe_commands.add_parser(
        "pair", help="Generate unapproved start/end frames with OpenPose"
    )
    pair.add_argument("--shot-id", required=True)
    pair.add_argument("--character-id", default="akira")
    pair.add_argument("--outfit-id", default="akira-default")
    pair.add_argument("--prompt-start", required=True)
    pair.add_argument("--prompt-end", required=True)
    pair.add_argument("--start-pose", required=True)
    pair.add_argument("--end-pose", required=True)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    container_factory: Callable[[], AnimationContainer] = create_container,
) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "character":
            if arguments.character_command == "show":
                _show_character(
                    _load_character_bible(arguments.input)
                    if arguments.input
                    else CharacterBible.akira()
                )
            elif arguments.character_command == "init":
                _initialize_character(arguments)
            elif arguments.character_command == "plan":
                _plan_character(arguments)
            elif arguments.character_command == "dataset":
                return _build_character_dataset(arguments)
            elif arguments.character_command == "audit-dataset":
                return _audit_character_dataset(arguments)
            elif arguments.character_command == "review-template":
                return _create_character_review_template(arguments)
            elif arguments.character_command == "train":
                return asyncio.run(_train_character_lora(arguments))
            else:
                return asyncio.run(
                    _run_character_generation(arguments, container_factory())
                )
        elif arguments.command == "background":
            if arguments.background_command == "init":
                _initialize_background(arguments)
            elif arguments.background_command == "plan":
                _plan_background(arguments)
            elif arguments.background_command == "approve":
                _approve_backgrounds(arguments)
            else:
                return asyncio.run(
                    _generate_backgrounds(arguments, container_factory())
                )
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
        elif arguments.command == "keyframe":
            return asyncio.run(_run_keyframe_commands(arguments, container_factory()))
        return 0
    except Exception as error:  # noqa: BLE001 - CLI boundary
        print(f"SELMA command failed: {error}", file=sys.stderr)
        return 1


def _show_character(bible: CharacterBible) -> None:
    payload = bible.to_dict()
    payload["prompt_fragments"] = list(bible.prompt_fragments())
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _initialize_character(arguments: argparse.Namespace) -> None:
    from core.application.services.character_bible_factory_service import (
        CharacterBibleFactoryService,
    )

    brief = json.loads(Path(arguments.brief).read_text(encoding="utf-8"))
    if not isinstance(brief, dict):
        raise TypeError("Character brief JSON must contain an object.")
    bible = CharacterBibleFactoryService().create(brief)
    print(
        _write_json(
            arguments.output,
            {"schema_version": 1, "character_bible": bible.to_dict()},
        )
    )


def _load_character_bible(path: str | Path) -> CharacterBible:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Character Bible JSON must contain an object.")
    bible_payload = payload.get("character_bible", payload)
    if not isinstance(bible_payload, dict):
        raise TypeError("character_bible must contain an object.")
    return CharacterBible.from_dict(bible_payload)


def _write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target.resolve()


def _initialize_background(arguments: argparse.Namespace) -> None:
    from core.application.services.location_bible_factory_service import (
        LocationBibleFactoryService,
    )

    brief = json.loads(Path(arguments.brief).read_text(encoding="utf-8"))
    if not isinstance(brief, dict):
        raise TypeError("Location brief JSON must contain an object.")
    location = LocationBibleFactoryService().create(brief)
    print(
        _write_json(
            arguments.output,
            {"schema_version": 1, "location_bible": location.to_dict()},
        )
    )


def _load_location_bible(path: str | Path):
    from core.domain.entities.location_bible import LocationBible

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Location Bible JSON must contain an object.")
    data = payload.get("location_bible", payload)
    if not isinstance(data, dict):
        raise TypeError("location_bible must contain an object.")
    return LocationBible.from_dict(data)


def _plan_background(arguments: argparse.Namespace) -> None:
    from core.application.services.background_factory_service import (
        BackgroundFactoryService,
    )

    plan = BackgroundFactoryService.plan(_load_location_bible(arguments.input))
    print(_write_json(arguments.output, plan.to_dict()))


async def _generate_backgrounds(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> int:
    pack = await container.background_factory_service.generate(
        _load_location_bible(arguments.input),
        output_prefix=arguments.output_prefix,
    )
    print(_write_json(arguments.manifest, pack.to_dict()))
    return 0


def _approve_backgrounds(arguments: argparse.Namespace) -> None:
    from dataclasses import replace

    location = _load_location_bible(arguments.input)
    manifest = json.loads(Path(arguments.manifest).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise TypeError("Background manifest must contain an object.")
    if str(manifest.get("location_id")) != location.location_id:
        raise ValueError("Background manifest does not belong to this Location Bible.")
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 12:
        raise ValueError("Background approval requires all 12 coverage candidates.")
    keys: list[str] = []
    for raw in candidates:
        if not isinstance(raw, dict):
            raise TypeError("Every background candidate must contain an object.")
        key = str(raw.get("storage_key", ""))
        quality = raw.get("quality")
        if "/source/" not in key or not key.endswith(".png"):
            raise ValueError("Only accepted source PNGs may be approved.")
        if quality is not None and (
            not isinstance(quality, dict) or not bool(quality.get("passed"))
        ):
            raise ValueError("A failed automatic quality result cannot be approved.")
        keys.append(key)
    if len(keys) != len(set(keys)):
        raise ValueError("Background approval contains duplicate candidates.")
    locked = replace(location, locked=True)
    print(
        _write_json(
            arguments.output,
            {
                "schema_version": 1,
                "approval": {
                    "approved_by": arguments.approved_by,
                    "background_pack_approved": True,
                    "approved_storage_keys": keys,
                },
                "location_bible": locked.to_dict(),
            },
        )
    )


def _plan_character(arguments: argparse.Namespace) -> None:
    from core.application.services.character_onboarding_service import (
        CharacterOnboardingService,
    )

    character = _load_character_bible(arguments.input)
    plan = CharacterOnboardingService.plan(character)
    print(_write_json(arguments.output, plan.to_dict()))


def _build_character_dataset(arguments: argparse.Namespace) -> int:
    from core.application.services.character_lora_dataset_service import (
        CharacterLoraDatasetService,
    )
    from core.application.services.character_onboarding_service import (
        CharacterOnboardingService,
    )

    character = _load_character_bible(arguments.input)
    planned_token = CharacterOnboardingService.plan(character).trigger_token
    trigger_token = arguments.trigger_token or f"{planned_token.rsplit('_v', 1)[0]}_v2"
    report = CharacterLoraDatasetService().build(
        source_dir=arguments.source,
        output_dir=arguments.output,
        character_id=character.character_id,
        trigger_token=trigger_token,
        character_bible=character,
        review_manifest=arguments.review_manifest,
        canonical_anchor=arguments.canonical_anchor,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.is_ready else 2


def _audit_character_dataset(arguments: argparse.Namespace) -> int:
    from core.application.services.character_lora_dataset_audit_service import (
        CharacterLoraDatasetAuditService,
    )

    audit = CharacterLoraDatasetAuditService().audit(arguments.manifest)
    payload = audit.to_dict()
    if arguments.output:
        print(_write_json(arguments.output, payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if audit.training_approved else 2


def _create_character_review_template(arguments: argparse.Namespace) -> int:
    from core.application.services.character_lora_dataset_audit_service import (
        CharacterLoraDatasetAuditService,
    )

    payload = CharacterLoraDatasetAuditService().create_review_template(
        manifest_path=arguments.manifest,
        canonical_anchor=arguments.canonical_anchor,
    )
    print(_write_json(arguments.output, payload))
    return 0


async def _train_character_lora(arguments: argparse.Namespace) -> int:
    from core.domain.value_objects.character_lora_training import (
        CharacterLoraTrainingRequest,
    )
    from infrastructure.providers.training.kohya_character_lora_trainer import (
        KohyaCharacterLoraTrainer,
    )

    character = _load_character_bible(arguments.input)
    request = CharacterLoraTrainingRequest(
        character_id=character.character_id,
        dataset_dir=Path(arguments.dataset),
        base_model_path=Path(arguments.base_model),
        output_dir=Path(arguments.output),
        model_name=arguments.model_name,
        max_train_steps=arguments.steps,
    )
    result = await KohyaCharacterLoraTrainer(arguments.sd_scripts_dir).train(request)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


async def _run_character_generation(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> int:
    character = _load_character_bible(arguments.input)
    service = container.character_onboarding_service
    if arguments.character_command == "anchor":
        if not 1 <= arguments.count <= 8:
            raise ValueError("Anchor candidate count must be between 1 and 8.")
        candidates = [
            await service.generate_anchor(
                character,
                output_prefix=arguments.output_prefix,
                seed_offset=index * 10_000,
                source_reference_storage_key=arguments.source_reference_key,
            )
            for index in range(arguments.count)
        ]
        print(
            json.dumps(
                {
                    "character_id": character.character_id,
                    "candidates": [candidate.to_dict() for candidate in candidates],
                    "human_approved": False,
                    "next_gate": "HUMAN_ANCHOR_APPROVAL",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if arguments.character_command == "references":
        from core.domain.value_objects.character_onboarding import (
            CharacterPilotApproval,
        )

        pilot_approval = None
        if arguments.pilot_approval:
            raw_approval = json.loads(
                Path(arguments.pilot_approval).read_text(encoding="utf-8")
            )
            if not isinstance(raw_approval, dict):
                raise TypeError("Pilot approval receipt must contain an object.")
            pilot_approval = CharacterPilotApproval.from_dict(raw_approval)
        pack = await service.generate_reference_pack(
            character,
            anchor_storage_key=arguments.approved_anchor_key,
            output_prefix=arguments.output_prefix,
            recipe_limit=arguments.limit,
            automatic_review=not arguments.defer_visual_review,
            pilot_approval=pilot_approval,
        )
        payload = {
            **pack.to_dict(),
            "automatic_review_deferred": arguments.defer_visual_review,
            "pack_complete": len(pack.candidates) == 23,
        }
        print(_write_json(arguments.manifest, payload))
        return 0
    if arguments.character_command == "approve-pilot":
        checks = {
            name: bool(getattr(arguments, name))
            for name in (
                "face_match",
                "hair_match",
                "immutable_marks_match",
                "outfit_match",
                "framing_match",
                "anatomy_pass",
            )
        }
        approval = await service.approve_pilot(
            character,
            anchor_storage_key=arguments.approved_anchor_key,
            pilot_storage_key=arguments.pilot_key,
            approved_by=arguments.approved_by,
            checks=checks,
        )
        print(_write_json(arguments.output, approval.to_dict()))
        return 0
    if arguments.character_command == "approve-references":
        from dataclasses import replace

        from core.domain.services.character_bible_validation_service import (
            CharacterBibleValidationService,
        )
        from core.domain.value_objects.character_identity import ReferenceView

        approval = json.loads(Path(arguments.selections).read_text(encoding="utf-8"))
        if not isinstance(approval, dict) or not isinstance(
            approval.get("views"), dict
        ):
            raise TypeError("Reference selections must contain a views object.")
        selected = {
            ReferenceView(str(view)): str(storage_key)
            for view, storage_key in approval["views"].items()
        }
        character = await service.approve_reference_pack(character, selected)
        if arguments.lock_narrative:
            if character.narrative_profile is None:
                raise ValueError("Character has no narrative profile to lock.")
            character.narrative_profile = replace(
                character.narrative_profile, locked=True
            )
        report = CharacterBibleValidationService().validate(character)
        if not report.is_complete:
            raise ValueError("Approved references unexpectedly became invalid.")
        print(
            _write_json(
                arguments.output,
                {
                    "schema_version": 1,
                    "approval": {
                        "approved_by": arguments.approved_by,
                        "reference_pack_approved": True,
                        "narrative_locked": bool(
                            character.narrative_profile
                            and character.narrative_profile.locked
                        ),
                    },
                    "character_bible": character.to_dict(),
                },
            )
        )
        return 0
    raise ValueError(f"Unsupported character command: {arguments.character_command}")


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
        matches = [
            item for item in characters if item.character_id == arguments.character_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"The locked Character Bible '{arguments.character_id}' "
                "was not found exactly once."
            )
        golden_set = await container.character_golden_set_service.run(
            character=matches[0],
            style=visual,
            model_id=arguments.model_id,
            model_revision=arguments.model_revision,
        )
        target = Path(
            arguments.output
            or f"output/preproduction/{arguments.character_id}-golden-set.json"
        )
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


async def _run_keyframe_commands(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> int:
    if arguments.keyframe_command != "pair":
        raise ValueError(f"Unsupported keyframe command: {arguments.keyframe_command}")

    from core.domain.entities.character_state import CharacterState
    from core.domain.entities.shot_animation import AnimationShotPlan

    shot = AnimationShotPlan(
        id=arguments.shot_id,
        script_id="keyframe-pair",
        scene_plan_id="keyframe-pair",
        prompt=arguments.prompt_start,
        prompt_end=arguments.prompt_end,
        duration_seconds=2.0,
        character_state=CharacterState(
            character_id=arguments.character_id,
            active_outfit_id=arguments.outfit_id,
            injuries=[],
            held_objects=[],
        ),
        start_pose_reference_key=arguments.start_pose,
        end_pose_reference_key=arguments.end_pose,
        controlnet_type="openpose",
    )
    pair = await container.keyframe_generation_service.generate_keyframe_pair(shot)
    print(
        json.dumps(
            {
                "shot_id": arguments.shot_id,
                "start_storage_key": pair.start_storage_key,
                "end_storage_key": pair.end_storage_key,
                "human_approved": pair.human_approved,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
