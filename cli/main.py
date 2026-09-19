from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cli.parsers import build_parser
from config.container import AnimationContainer, create_container
from core.application.services.hierarchical_shot_planning_service import (
    HierarchicalShotPlanningService,
)
from core.application.services.script_breakdown_service import ScriptBreakdownService
from core.domain.entities.character_bible import CharacterBible
from core.domain.entities.episode_script import EpisodeScript
from core.domain.entities.shot_animation import ShotPlan
from core.domain.value_objects.story_review import StoryDevelopmentResult

logger = logging.getLogger(__name__)


def main(
    argv: Sequence[str] | None = None,
    *,
    container_factory: Callable[[], AnimationContainer] = create_container,
) -> int:
    arguments = build_parser().parse_args(argv)
    from config.settings import get_settings, warn_if_offline_test_profile

    warn_if_offline_test_profile(get_settings())
    try:
        if arguments.command == "series":
            from cli.series_commands import run_series_command

            return run_series_command(arguments)
        if arguments.command == "character":
            if arguments.character_command == "show":
                _show_character(_load_character_bible(arguments.input))
            elif arguments.character_command == "init":
                _initialize_character(arguments)
            elif arguments.character_command == "lock-narrative":
                _lock_character_narrative(arguments)
            elif arguments.character_command == "plan":
                _plan_character(arguments)
            elif arguments.character_command in {
                "dataset",
                "audit-dataset",
                "review-template",
                "view-consistency-report",
                "drift-report",
                "qc-calibration-create",
                "qc-calibration-summarize",
                "train",
                "benchmark-validate",
            }:
                from cli.character_quality_commands import (
                    run_character_quality_command,
                )

                return run_character_quality_command(
                    arguments,
                    write_json=_write_json,
                    load_character_bible=_load_character_bible,
                    load_creation_brief=_load_character_creation_brief,
                )
            else:
                from cli.character_asset_commands import (
                    run_character_asset_command,
                )

                return asyncio.run(
                    run_character_asset_command(
                        arguments,
                        container_factory(),
                        write_json=_write_json,
                        load_character_bible=_load_character_bible,
                        load_creation_brief=_load_character_creation_brief,
                        container_factory=container_factory,
                    )
                )
        elif arguments.command == "background":
            from cli.background_commands import run_background_command

            return run_background_command(
                arguments,
                write_json=_write_json,
                container_factory=container_factory,
            )
        elif arguments.command == "episode":
            return _run_episode_command(arguments, container_factory=container_factory)
        elif arguments.command == "pilot":
            from cli.pilot_commands import run_pilot_command

            return run_pilot_command(
                arguments,
                write_json=_write_json,
                awaitable_run=awaitable_run,
            )
        elif arguments.command == "trailer":
            return _run_trailer_command(arguments)
        elif arguments.command == "script":
            _break_down_script(arguments)
        elif arguments.command == "story":
            return asyncio.run(
                _run_story_commands(arguments, container_factory())
            )
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


def _lock_character_narrative(arguments: argparse.Namespace) -> None:
    """Lock narrative canon alone; a visual reference pack is a separate claim.

    The story gate needs narrative canon, not rendered assets. Requiring a
    reference pack to lock a profile would force artwork before the screenplay
    is approved, so this records the human signature on its own.
    """
    from dataclasses import replace

    bible = _load_character_bible(arguments.input)
    profile = bible.narrative_profile
    if profile is None:
        raise ValueError("Character has no narrative profile to lock.")
    if profile.locked:
        raise ValueError(
            "Character narrative profile is already locked. Changing locked "
            "canon needs an explicit revision, not a silent re-lock."
        )
    approver = arguments.approved_by.strip()
    if not approver:
        raise ValueError("approved_by must not be empty.")

    locked_bible = replace(bible, narrative_profile=replace(profile, locked=True))
    _write_json(
        arguments.output,
        {"schema_version": 1, "character_bible": locked_bible.to_dict()},
    )

    canon_payload = {**profile.to_dict(), "locked": False}
    receipt = _write_json(
        arguments.receipt
        or Path("output/preproduction/narrative-locks")
        / f"{bible.character_id}.json",
        {
            "schema_version": 1,
            "character_id": bible.character_id,
            "approved_by": approver,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "narrative_locked": True,
            "narrative_hash": hashlib.sha256(
                json.dumps(canon_payload, ensure_ascii=False, sort_keys=True).encode(
                    "utf-8"
                )
            ).hexdigest(),
            "visual_readiness_claimed": False,
        },
    )
    print(str(receipt))


def _load_character_bible(path: str | Path) -> CharacterBible:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Character Bible JSON must contain an object.")
    bible_payload = payload.get("character_bible", payload)
    if not isinstance(bible_payload, dict):
        raise TypeError("character_bible must contain an object.")
    return CharacterBible.from_dict(bible_payload)


def _load_character_creation_brief(path: str | Path):
    from core.domain.value_objects.character_creation_brief import (
        CharacterCreationBrief,
    )

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Character creation brief JSON must contain an object.")
    brief_payload = payload.get("character_creation_brief", payload)
    if not isinstance(brief_payload, dict):
        raise TypeError("character_creation_brief must contain an object.")
    brief = CharacterCreationBrief.from_dict(brief_payload)
    source = Path(path)
    lock_path = source.with_name(f"{source.stem}.lock.json")
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if not isinstance(lock, dict) or lock.get("status") != "LOCKED":
            raise ValueError(f"Character brief lock is malformed: {lock_path}")
        if lock.get("brief_hash") != brief.content_hash:
            raise ValueError(
                "Character brief changed after approval; review and refresh its lock."
            )
    return brief


def _write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return target.resolve()

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
    if arguments.character_command == "pose-pack":
        from core.application.services.character_pose_pack_batch_service import (
            CharacterPosePackBatchService,
        )
        from core.domain.value_objects.character_design import (
            CharacterCanonicalApproval,
        )

        if arguments.pose_pack_command == "generate":
            brief = _load_character_creation_brief(arguments.brief)
            raw_approval = json.loads(Path(arguments.approval).read_text(encoding="utf-8"))
            if not isinstance(raw_approval, dict):
                raise TypeError("Canonical approval receipt must contain an object.")
            manifest = await container.character_pose_pack_service.generate_pack(
                brief,
                CharacterCanonicalApproval.from_dict(raw_approval),
                active_series_path=arguments.active_series,
                mode="PRODUCTION",
                output_prefix=arguments.output_prefix,
                run_id=arguments.run_id,
            )
            print(_write_json(arguments.manifest, manifest.to_dict()))
            return 0
        if arguments.pose_pack_command == "approve":
            approval = await container.character_pose_pack_service.approve_pack(
                manifest_storage_key=arguments.manifest,
                approved_by=arguments.approved_by,
                confirmed_checks=list(arguments.checks or []),
            )
            print(json.dumps(approval.to_dict(), ensure_ascii=False, indent=2))
            return 0
        raw_jobs = json.loads(Path(arguments.jobs).read_text(encoding="utf-8"))
        if not isinstance(raw_jobs, list) or not all(isinstance(item, dict) for item in raw_jobs):
            raise TypeError("Pose-pack batch jobs must be a JSON list of objects.")
        payload = await CharacterPosePackBatchService(
            container.character_pose_pack_service,
            style_lock_resolver=container.style_lock_service,
        ).run(
            raw_jobs,
            output_manifest=arguments.manifest,
            continue_on_error=not arguments.stop_on_error,
            active_series_path=arguments.active_series,
            workflow_path=arguments.workflow,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if arguments.character_command == "benchmark-run":
        from config.settings import get_settings
        from core.application.services.character_model_tournament_service import (
            CharacterModelTournamentService,
        )
        from infrastructure.providers.keyframe.comfyui_memory_releaser import (
            ComfyUiMemoryReleaser,
        )

        workspace_root = Path(__file__).resolve().parents[1]
        base_settings = get_settings()
        brief = _load_character_creation_brief(arguments.brief)
        run_id = arguments.run_id or datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        def generator_factory(model_lock_path: Path):
            settings = base_settings.model_copy(
                update={
                    "keyframe_generation_provider": "comfyui",
                    "comfyui_model_lock_path": str(model_lock_path),
                    "comfyui_keyframe_checkpoint": "",
                }
            )
            return create_container(settings=settings).character_design_service

        report = await CharacterModelTournamentService(
            workspace_root,
            generator_factory,
            ComfyUiMemoryReleaser(base_settings.comfyui_api_url).release,
        ).run(
            benchmark_path=arguments.benchmark,
            brief=brief,
            model_lock_paths=arguments.model_locks,
            count=arguments.count,
            run_id=run_id,
        )
        print(_write_json(arguments.output, report))
        return 0
    if arguments.character_command == "benchmark-validate":
        from core.application.services.character_quality_benchmark_service import (
            CharacterQualityBenchmarkService,
        )

        workspace_root = Path(__file__).resolve().parents[1]
        benchmark = CharacterQualityBenchmarkService(workspace_root).validate(
            arguments.benchmark
        )
        print(
            json.dumps(
                {
                    "status": "VALID",
                    "benchmark": benchmark.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if arguments.character_command == "create":
        brief = _load_character_creation_brief(arguments.brief)
        pack = await container.character_design_service.generate_candidates(
            brief,
            count=arguments.count,
            output_prefix=arguments.output_prefix,
            run_id=arguments.run_id,
            style_reference_path=arguments.style_reference,
            style_weight=arguments.style_weight,
        )
        print(_write_json(arguments.manifest, pack.to_dict()))
        return 0
    if arguments.character_command == "approve-design":
        from core.domain.value_objects.character_design import CharacterDesignCandidate

        brief = _load_character_creation_brief(arguments.brief)
        manifest = json.loads(Path(arguments.manifest).read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise TypeError("Character design manifest must contain an object.")
        if (
            manifest.get("character_id") != brief.character_id
            or manifest.get("brief_hash") != brief.content_hash
        ):
            raise ValueError("Character design manifest belongs to another brief.")
        raw_candidates = manifest.get("candidates")
        if not isinstance(raw_candidates, list):
            raise TypeError("Character design manifest must contain candidates.")
        selected = next(
            (
                item
                for item in raw_candidates
                if isinstance(item, dict)
                and item.get("storage_key") == arguments.candidate_key
            ),
            None,
        )
        if selected is None:
            raise ValueError(
                "Selected design candidate is not present in the manifest."
            )
        design_approval = await container.character_canonical_approval_service.approve_candidate(
            brief,
            CharacterDesignCandidate.from_dict(selected),
            approved_by=arguments.approved_by,
            character_version=arguments.version,
            output_prefix=arguments.output_prefix,
            brief_consistency_confirmed=bool(arguments.confirm_brief_consistency),
        )
        print(_write_json(arguments.output, design_approval.to_dict()))
        return 0
    if arguments.character_command == "turnaround":
        from core.domain.value_objects.character_design import (
            CharacterCanonicalApproval,
        )

        brief = _load_character_creation_brief(arguments.brief)
        raw_approval = json.loads(Path(arguments.approval).read_text(encoding="utf-8"))
        if not isinstance(raw_approval, dict):
            raise TypeError("Canonical approval receipt must contain an object.")
        view_pack = await container.character_view_pack_generation_service.generate_canonical_views(
            brief,
            CharacterCanonicalApproval.from_dict(raw_approval),
            output_prefix=arguments.output_prefix,
            # Without this the --seeds flag was accepted and then ignored, so a
            # requested sweep silently rendered a single seed per view.
            view_candidate_count=arguments.seeds,
        )
        print(_write_json(arguments.manifest, view_pack.to_dict()))
        return 0
    if arguments.character_command == "approve-view-pack":
        raw_version = str(arguments.version).strip().casefold().removeprefix("v")
        view_pack_approval = await container.character_view_pack_generation_service.approve_view_pack(
            character_id=arguments.character,
            character_version=int(raw_version),
            approved_by=arguments.approved_by,
            output_prefix=arguments.output_prefix,
            acceptance_path=arguments.acceptance,
            confirmed_checks=list(arguments.checks or []),
        )
        payload = view_pack_approval.to_dict()
        if arguments.output:
            print(_write_json(arguments.output, payload))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
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
        pose_references = None
        if arguments.pose_references:
            raw_pose_references = json.loads(
                Path(arguments.pose_references).read_text(encoding="utf-8")
            )
            if not isinstance(raw_pose_references, dict) or not all(
                isinstance(view, str) and isinstance(storage_key, str)
                for view, storage_key in raw_pose_references.items()
            ):
                raise TypeError(
                    "Pose references must be a JSON object of view-to-storage-key strings."
                )
            pose_references = raw_pose_references
        reference_pack = await service.generate_reference_pack(
            character,
            anchor_storage_key=arguments.approved_anchor_key,
            output_prefix=arguments.output_prefix,
            recipe_limit=arguments.limit,
            recipe_offset=arguments.recipe_offset,
            automatic_review=not arguments.defer_visual_review,
            pilot_approval=pilot_approval,
            seed_offset=arguments.seed_offset,
            pose_references=pose_references,
        )
        payload = {
            **reference_pack.to_dict(),
            "automatic_review_deferred": arguments.defer_visual_review,
            "pack_complete": len(reference_pack.candidates) == 23,
            "seed_offset": arguments.seed_offset,
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
        pilot_approval = await service.approve_pilot(
            character,
            anchor_storage_key=arguments.approved_anchor_key,
            pilot_storage_key=arguments.pilot_key,
            approved_by=arguments.approved_by,
            checks=checks,
        )
        print(_write_json(arguments.output, pilot_approval.to_dict()))
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
        validation_report = CharacterBibleValidationService().validate(character)
        if not validation_report.is_complete:
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


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"JSON file must contain an object: {path}")
    return payload


def _load_episode_plan_inputs(arguments: argparse.Namespace):
    from core.application.services.asset_approval_service import AssetApprovalService
    from core.domain.value_objects.asset_approval import AssetApprovalReceipt
    from core.domain.value_objects.background_production import (
        BackgroundCandidate,
        BackgroundCandidatePack,
    )
    from core.domain.value_objects.character_pose_pack import (
        CharacterPosePackApproval,
        CharacterPosePackManifest,
    )

    characters = [_load_character_bible(path) for path in arguments.character_bibles]
    from cli.background_commands import _load_location_bible

    locations = [_load_location_bible(path) for path in arguments.location_bibles]
    pose_packs = {}
    for path in arguments.pose_packs:
        payload = _load_json_object(path)
        manifest_payload = payload.get("manifest", payload)
        manifest = CharacterPosePackManifest.from_dict(manifest_payload)
        approval_path = Path(path).with_name("approval.json")
        if approval_path.is_file() and manifest_payload is payload:
            approval = CharacterPosePackApproval.from_dict(
                _load_json_object(approval_path)
            )
            import hashlib
            manifest_bytes = Path(path).read_bytes()
            expected_pose_hashes = {
                pose.pose_id: pose.content_hash for pose in manifest.poses
            }
            shared_receipt = _load_json_object(approval_path).get("asset_approval_receipt")
            shared_valid = False
            if isinstance(shared_receipt, dict):
                try:
                    shared_valid = AssetApprovalService.verify(
                        AssetApprovalReceipt.from_dict(shared_receipt),
                        asset_hash=AssetApprovalService.asset_set_digest(
                            [pose.content_hash for pose in manifest.poses]
                        ),
                        manifest_payload=manifest.to_dict(),
                    )
                except Exception:
                    shared_valid = False
            if (
                hashlib.sha256(manifest_bytes).hexdigest()
                == approval.manifest_content_hash
                and approval.character_id == manifest.character_id
                and approval.character_version == manifest.character_version
                and dict(approval.pose_hashes) == expected_pose_hashes
                and shared_valid
            ):
                from dataclasses import replace
                manifest = replace(
                    manifest,
                    human_approved=True,
                    approval_receipt=shared_receipt,
                )
        pose_packs[manifest.character_id] = manifest
    background_packs = {}
    for path in arguments.background_packs:
        payload = _load_json_object(path)
        raw_candidates = payload.get("candidates", [])
        if not isinstance(raw_candidates, list):
            raise TypeError("Background candidate pack candidates must be a list.")
        candidates = tuple(
            BackgroundCandidate(
                recipe_id=str(item.get("recipe_id", "")),
                storage_key=str(item.get("storage_key", "")),
                width=int(item.get("width", 0)),
                height=int(item.get("height", 0)),
                attempt=int(item.get("attempt", 1)),
                content_hash=str(item.get("content_hash", "")),
            )
            for item in raw_candidates
            if isinstance(item, dict)
        )
        approval = payload.get("approval", {})
        raw_receipt = payload.get("approval_receipt")
        pack = BackgroundCandidatePack(
            location_id=str(payload.get("location_id", "")),
            candidates=candidates,
            human_approved=False,
            approval_receipt=(dict(raw_receipt) if isinstance(raw_receipt, dict) else None),
        )
        if isinstance(raw_receipt, dict):
            try:
                pack = BackgroundCandidatePack(
                    location_id=pack.location_id,
                    candidates=pack.candidates,
                    human_approved=AssetApprovalService.verify(
                        AssetApprovalReceipt.from_dict(raw_receipt),
                        asset_hash=AssetApprovalService.asset_set_digest(
                            [candidate.content_hash for candidate in candidates]
                        ),
                        manifest_payload=pack.to_dict(),
                    ),
                    approval_receipt=raw_receipt,
                )
            except Exception as error:
                # A receipt that does not verify leaves the pack unapproved; the
                # reference project must not silently claim human approval.
                logger.warning(
                    "Ignoring unverifiable approval receipt for background pack "
                    "'%s': %s",
                    pack.location_id,
                    error,
                )
        background_packs[pack.location_id] = pack
    non_cast_voices: tuple[Any, ...] = ()
    if getattr(arguments, "world_bible", None):
        from core.domain.entities.direction_bible import WorldBible

        world_payload = _load_json_object(arguments.world_bible)
        world = WorldBible.from_dict(
            dict(world_payload.get("world_bible", world_payload))
        )
        non_cast_voices = world.non_cast_voices
    return characters, locations, pose_packs, background_packs, non_cast_voices


def _episode_director_provider(arguments: argparse.Namespace):
    if getattr(arguments, "director_provider", "rules") == "rules":
        return None
    if arguments.director_provider == "claude":
        from config.settings import get_settings
        from infrastructure.providers.episode_director.claude_episode_director_provider import (
            ClaudeEpisodeDirectorProvider,
        )

        settings = get_settings()
        return ClaudeEpisodeDirectorProvider(
            api_key=settings.anthropic_api_key,
            model=arguments.director_model,
        )
    raise ValueError(f"Unsupported Episode Director provider: {arguments.director_provider}")


def _run_trailer_command(arguments: argparse.Namespace) -> int:
    from core.application.services.trailer_cli_service import TrailerCliService

    service = TrailerCliService()
    if arguments.trailer_command == "init":
        payload = service.init(arguments.trailer_id)
        print(_write_json(arguments.output, payload))
        return 0
    if arguments.trailer_command == "plan":
        episode = service.load(arguments.input)
        brief = service.load(arguments.brief) if arguments.brief else None
        payload = service.plan(episode, brief)
        print(_write_json(arguments.output, payload))
        return 0
    if arguments.trailer_command == "package":
        from core.application.services.wan22_package_service import Wan22PackageService
        from core.domain.value_objects.trailer_plan import TrailerPlan
        plan = TrailerPlan.from_dict(service.load(arguments.input))
        sources = service.load(arguments.sources)
        packages = Wan22PackageService().build(plan, sources)
        print(_write_json(arguments.output, {"schema_version": 1, "trailer_id": plan.timeline.trailer_id, "packages": [item.to_dict() for item in packages]}))
        return 0
    if arguments.trailer_command == "animatic":
        from core.application.services.trailer_animatic_service import TrailerAnimaticService
        from core.domain.value_objects.trailer_audio_cue import TrailerAudioCue
        from core.domain.value_objects.trailer_plan import TrailerPlan
        from infrastructure.storage.local_fs_storage import LocalFsStorage
        plan = TrailerPlan.from_dict(service.load(arguments.input))
        assets = service.load(arguments.assets) if arguments.assets else {}
        raw_cues = service.load(arguments.audio_cues) if arguments.audio_cues else []
        if isinstance(raw_cues, dict):
            raw_cues = raw_cues.get("audio_cues", [])
        if not isinstance(raw_cues, list):
            raise TypeError("Audio cues must contain a JSON list.")
        audio_cues = tuple(
            TrailerAudioCue.from_dict(item)
            for item in raw_cues
            if isinstance(item, dict)
        )
        storage = LocalFsStorage(arguments.storage_root)
        animatic_service = TrailerAnimaticService(storage)

        async def build_trailer_animatic():
            normalized_assets, audio_diagnostics = await animatic_service.prepare_audio_assets(
                plan, assets, shot_ids=arguments.shot_ids or None
            )
            built_project = await animatic_service.build(
                plan,
                assets=normalized_assets,
                shot_ids=arguments.shot_ids or None,
                audio_cues=audio_cues,
                mode=arguments.mode,
            )
            return built_project, audio_diagnostics

        project, audio_diagnostics = asyncio.run(build_trailer_animatic())
        audio_blocked = arguments.mode == "STRICT" and any(
            item.get("status") != "OK" for item in audio_diagnostics
        )
        payload = {
            "status": "BLOCKED" if audio_blocked else ("READY_FOR_REVIEW" if project else "BLOCKED"),
            "mode": arguments.mode,
            "project_kind": "TRAILER",
            "animatic_project": project.to_dict() if project and not audio_blocked else None,
            "audio_diagnostics": list(audio_diagnostics),
        }
        if audio_blocked:
            print(_write_json(arguments.output, payload))
            return 2
        if project is not None and arguments.render:
            from core.application.services.animatic_render_service import (
                AnimaticRenderService,
            )
            from infrastructure.providers.render.ffprobe_media_inspection_provider import (
                FfprobeMediaInspectionProvider,
            )
            from infrastructure.providers.render.remotion_animatic_exporter import (
                RemotionAnimaticExporter,
            )
            props_path = asyncio.run(RemotionAnimaticExporter(storage, arguments.motion_public_dir).export(project))
            render_result = asyncio.run(AnimaticRenderService(
                motion_directory="motion",
                inspector=FfprobeMediaInspectionProvider(),
            ).render(
                project, props_path=props_path,
                output_path=arguments.render_output or str(Path(arguments.output).with_suffix(".mp4")),
            ))
            payload["render"] = render_result.to_dict()
            if render_result.status != "READY_FOR_REVIEW":
                print(_write_json(arguments.output, payload))
                return 3
        print(_write_json(arguments.output, payload))
        return 0
    if arguments.trailer_command == "preflight":
        from core.application.services.wan22_package_service import Wan22PackageService
        print(json.dumps(Wan22PackageService.preflight(arguments.worker), ensure_ascii=False, indent=2))
        return 0
    if arguments.trailer_command == "inspect":
        plan_payload = service.load(arguments.input)
        shots = plan_payload.get("shots", [])
        timeline = plan_payload.get("timeline", {})
        summary = {
            "trailer_id": plan_payload.get("timeline", {}).get("trailer_id", ""),
            "fps": timeline.get("fps"),
            "duration_frames": timeline.get("duration_frames"),
            "shot_count": len(shots) if isinstance(shots, list) else 0,
            "beat_count": len(timeline.get("beats", [])) if isinstance(timeline, dict) else 0,
            "warnings": plan_payload.get("warnings", []),
        }
        print(
            json.dumps(
                plan_payload if arguments.full else summary,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    raise ValueError(f"Unsupported trailer command: {arguments.trailer_command}")


def _run_episode_command(
    arguments: argparse.Namespace,
    *,
    container_factory: Callable[[], AnimationContainer] = create_container,
) -> int:
    from core.domain.value_objects.episode_director_plan import EpisodeDirectorPlan

    if arguments.episode_command == "animatic":
        from cli.episode_commands import run_episode_animatic_command

        return run_episode_animatic_command(
            arguments,
            load_json_object=_load_json_object,
            write_json=_write_json,
            awaitable_run=awaitable_run,
        )

    if arguments.episode_command == "inspect":
        payload = _load_json_object(arguments.input)
        plan = EpisodeDirectorPlan.from_dict(payload.get("episode_director_plan", payload))
        summary = {
            "episode_id": plan.episode_id,
            "title": plan.title,
            "decision_mode": plan.decision_mode,
            "provider": plan.provider,
            "fps": plan.fps,
            "total_duration_seconds": plan.total_duration_seconds,
            "duration_frames": plan.duration_frames,
            "scene_count": len(plan.scenes),
            "shot_count": sum(len(scene.shots) for scene in plan.scenes),
            "character_requirements": [item.to_dict() for item in plan.character_requirements],
            "background_requirements": [item.to_dict() for item in plan.background_requirements],
            "warnings": list(plan.warnings),
        }
        print(json.dumps(plan.to_dict() if arguments.full else summary, ensure_ascii=False, indent=2))
        return 0

    if arguments.episode_command not in {"plan", "prepare"}:
        raise ValueError(f"Unsupported episode command: {arguments.episode_command}")

    is_prepare = arguments.episode_command == "prepare"
    from core.application.services.episode_director_service import EpisodeDirectorService

    (
        characters,
        locations,
        pose_packs,
        background_packs,
        non_cast_voices,
    ) = _load_episode_plan_inputs(arguments)
    source = Path(arguments.input)
    raw = _load_json_object(source) if source.suffix.lower() == ".json" else None
    director = EpisodeDirectorService()
    provider = _episode_director_provider(arguments)
    if isinstance(raw, dict) and ("sequences" in raw or "episode_script" in raw):
        script_payload = raw.get("episode_script", raw)
        script = EpisodeScript.from_dict(dict(script_payload))
        planning_input: EpisodeScript | str = script
        plan_kwargs = {
            "character_bibles": characters,
            "locations": locations,
            "pose_packs": pose_packs,
            "background_packs": background_packs,
            "non_cast_voices": non_cast_voices,
            "episode_id": arguments.episode_id if arguments.episode_id != "episode-001" else None,
        }
        plan = awaitable_run(director.plan_with_provider(script, provider, **plan_kwargs)) if provider else director.plan_episode(script, **plan_kwargs)
    else:
        plan_kwargs = {
            "character_bibles": characters,
            "locations": locations,
            "pose_packs": pose_packs,
            "background_packs": background_packs,
            "non_cast_voices": non_cast_voices,
        }
        if source.suffix.lower() == ".fountain":
            from core.application.services.screenplay_normalization_service import (
                ScreenplayNormalizationService,
            )

            script = ScreenplayNormalizationService().from_fountain(
                source.read_text(encoding="utf-8"),
                script_id=arguments.episode_id,
                title=arguments.title,
            )
            planning_input = script
            plan_kwargs["episode_id"] = arguments.episode_id
            plan = (
                awaitable_run(director.plan_with_provider(script, provider, **plan_kwargs))
                if provider
                else director.plan_episode(script, **plan_kwargs)
            )
        else:
            screenplay_text = raw.get("script_text", "") if isinstance(raw, dict) else source.read_text(encoding="utf-8")
            planning_input = screenplay_text
            plan_kwargs.update({"episode_id": arguments.episode_id, "title": arguments.title})
            plan = (
                awaitable_run(director.plan_with_provider(screenplay_text, provider, **plan_kwargs))
                if provider
                else director.plan_text(screenplay_text, **plan_kwargs)
            )

    if is_prepare:
        from core.application.services.episode_preparation_service import (
            EpisodePreparationResult,
            EpisodePreparationService,
        )

        previous = None
        if arguments.resume:
            previous = EpisodePreparationResult.from_dict(
                _load_json_object(arguments.resume)
            )
        asset_generation = None
        generation_failures: dict[str, str] = {}
        if arguments.generate_assets:
            from core.application.services.episode_asset_generation_service import (
                EpisodeAssetGenerationService,
            )

            pose_jobs: list[dict[str, Any]] = []
            for path in arguments.pose_jobs:
                raw_job = _load_json_object(path)
                raw_jobs = raw_job.get("jobs", raw_job.get("pose_jobs", raw_job))
                if isinstance(raw_jobs, list):
                    pose_jobs.extend(
                        item for item in raw_jobs if isinstance(item, dict)
                    )
                elif isinstance(raw_jobs, dict):
                    pose_jobs.append(raw_jobs)
                else:
                    raise TypeError("Pose generation job JSON must contain an object or list.")
            if arguments.asset_mode == "DISCOVERY":
                from core.application.services.background_factory_service import (
                    BackgroundFactoryService,
                )
                from core.application.services.character_pose_pack_service import (
                    CharacterPosePackService,
                )
                from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
                    FakeKeyframeGenerationProvider,
                )
                from infrastructure.storage.local_fs_storage import LocalFsStorage

                discovery_storage = LocalFsStorage(
                    str(
                        Path(arguments.asset_output_root or Path(arguments.output).parent / "assets")
                        / "storage"
                    )
                )
                discovery_generator = FakeKeyframeGenerationProvider(sized_output=True)
                discovery_pose_service = CharacterPosePackService(
                    discovery_generator,
                    discovery_storage,
                    require_real_provenance=False,
                    default_mode="DISCOVERY",
                )
                discovery_background_service = BackgroundFactoryService(
                    discovery_generator,
                    discovery_storage,
                )
                from core.application.services.episode_asset_generation_service import (
                    EpisodeAssetGenerationService,
                )

                asset_service = EpisodeAssetGenerationService(
                    discovery_pose_service,
                    discovery_background_service,
                    discovery_storage,
                )
            else:
                container = container_factory()
                asset_service = container.episode_asset_generation_service
            generated = awaitable_run(
                asset_service.generate(
                    plan,
                    locations=tuple(locations),
                    pose_jobs=pose_jobs,
                    asset_mode=arguments.asset_mode,
                    output_root=(
                        arguments.asset_output_root
                        or Path(arguments.output).parent / "assets"
                    ),
                    active_series_path=arguments.active_series,
                    workflow_path=arguments.workflow,
                )
            )
            asset_generation = generated
            generation_failures = dict(generated.failures)
            if generated.pose_packs or generated.background_packs:
                regenerated_kwargs = {
                    **plan_kwargs,
                    "character_bibles": characters,
                    "locations": locations,
                    "pose_packs": {**pose_packs, **generated.pose_packs},
                    "background_packs": {**background_packs, **generated.background_packs},
                }
                plan = (
                    awaitable_run(director.plan_with_provider(planning_input, provider, **regenerated_kwargs))
                    if provider
                    else director.plan(planning_input, **regenerated_kwargs)
                )

        result = EpisodePreparationService().prepare(
            plan,
            previous=previous,
            retry_job_ids=tuple(arguments.retry_jobs or ()),
            failed_jobs=generation_failures,
        )
        payload = result.to_dict()
        if asset_generation is not None:
            payload["asset_generation"] = asset_generation.to_dict()
    else:
        payload = {"schema_version": 1, "episode_director_plan": plan.to_dict()}
    if arguments.output:
        print(_write_json(arguments.output, payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def awaitable_run(awaitable):
    """Run one async asset dispatch from the synchronous CLI boundary."""
    return asyncio.run(awaitable)


def _break_down_script(arguments: argparse.Namespace) -> None:
    source = Path(arguments.input)
    script_text = source.read_text(encoding="utf-8")
    service = ScriptBreakdownService(_load_character_bible(arguments.character_bible))
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


def _load_episode_script_input(
    path: str | Path, *, episode_id: str, title: str
) -> EpisodeScript:
    """Accept a normalized EpisodeScript JSON or a Fountain screenplay."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Screenplay input does not exist: {source}")
    suffix = source.suffix.lower()
    if suffix == ".json":
        payload = _load_json_object(source)
        script_payload = payload.get("episode_script", payload)
        if not isinstance(script_payload, dict):
            raise TypeError("episode_script must contain an object.")
        return EpisodeScript.from_dict(dict(script_payload))
    if suffix == ".fountain":
        from core.application.services.screenplay_normalization_service import (
            ScreenplayNormalizationService,
        )

        return ScreenplayNormalizationService().from_fountain(
            source.read_text(encoding="utf-8"),
            script_id=episode_id,
            title=title,
        )
    raise ValueError(
        f"Unsupported screenplay input '{source.suffix}'. Use .json or .fountain."
    )


def _story_review_report(
    script: EpisodeScript, result: StoryDevelopmentResult, *, source: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "input": source,
        "episode_script_id": script.id,
        "status": result.script.status.value,
        "ready_for_approval": result.ready_for_approval,
        "canon_report": {
            "passed": result.canon_report.passed,
            "violations": [
                {
                    "code": violation.code.value,
                    "message": violation.message,
                    "scene_id": violation.scene_id,
                    "evidence": violation.evidence,
                }
                for violation in result.canon_report.violations
            ],
        },
        "reviews": [
            {
                "reviewer": report.reviewer,
                "passed": report.passed,
                "issues": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "severity": issue.severity.value,
                        "scene_id": issue.scene_id,
                    }
                    for issue in report.issues
                ],
            }
            for report in result.reviews
        ],
    }


async def _run_story_commands(
    arguments: argparse.Namespace,
    container: AnimationContainer,
) -> int:
    """Refuse to lock a screenplay that has not passed canon and story review."""
    script = _load_episode_script_input(
        arguments.input,
        episode_id=arguments.episode_id,
        title=arguments.title,
    )
    engine = container.story_engine_service
    result = await engine.review(script)
    report = _story_review_report(
        script, result, source=str(Path(arguments.input).resolve())
    )
    if arguments.story_command == "review":
        _emit_story_report(report, arguments.output)
        return 0 if result.ready_for_approval else 1

    if not result.ready_for_approval:
        report["locked"] = False
        report["blocked_reason"] = (
            "Blocking canon violations or reviewer findings must be resolved "
            "before a human can lock this screenplay."
        )
        # --output means the locked screenplay. A blocked run must never leave
        # a file where a caller expects to find one.
        _emit_story_report(report, None)
        return 1

    locked = await engine.approve(result, approved_by=arguments.approved_by)
    payload = {
        "schema_version": 1,
        "episode_script": locked.to_dict(),
        "story_review": {
            **report,
            "status": locked.status.value,
            "locked": True,
            "approved_by": locked.approved_by,
            "approved_at": locked.approved_at.isoformat()
            if locked.approved_at
            else None,
        },
    }
    if arguments.output:
        print(str(_write_json(arguments.output, payload)))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _emit_story_report(report: dict[str, Any], output: str | None) -> None:
    if output:
        print(str(_write_json(output, report)))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


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

        if container.character_bible is None:
            raise ValueError(
                "register-views needs a character bible; the container was built "
                "without one."
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
        # The breakdown service needs a concrete bible, and the container is
        # built once for every command, so the identity is selected here rather
        # than injected. Nothing else built a bible, which is why this command
        # used to be reachable only from tests.
        characters = await container.canon_repository.get_character_bibles()
        matches = [
            item for item in characters if item.character_id == arguments.character_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"The locked Character Bible '{arguments.character_id}' "
                "was not found exactly once."
            )
        plan = HierarchicalShotPlanningService(
            ScriptBreakdownService(matches[0])
        ).plan(script)
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
    if arguments.keyframe_command == "approve-pair":
        approval = await container.keyframe_generation_service.approve_keyframe_pair(
            shot_id=arguments.shot_id,
            manifest_storage_key=arguments.manifest,
            approved_by=arguments.approved_by,
            confirmed_checks=list(arguments.checks or []),
        )
        print(json.dumps(approval.to_dict(), ensure_ascii=False, indent=2))
        return 0
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
                "manifest_storage_key": pair.manifest_storage_key,
                "contact_sheet_storage_key": pair.contact_sheet_storage_key,
                "human_approved": pair.human_approved,
            },
            indent=2,
        )
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
