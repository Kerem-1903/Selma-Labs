"""CLI handlers for character generation, onboarding, and approvals."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.container import AnimationContainer, create_container

JsonWriter = Callable[[str | Path, dict[str, Any]], Path]
CharacterLoader = Callable[[str | Path], Any]
BriefLoader = Callable[[str | Path], Any]


async def run_character_asset_command(
    arguments: argparse.Namespace,
    container: AnimationContainer,
    *,
    write_json: JsonWriter,
    load_character_bible: CharacterLoader,
    load_creation_brief: BriefLoader,
    container_factory: Callable[[], AnimationContainer] = create_container,
) -> int:
    """Handle character generation and approval commands outside the CLI entrypoint."""
    if arguments.character_command == "pose-pack":
        return await _run_pose_pack(
            arguments, container, write_json=write_json, load_creation_brief=load_creation_brief
        )
    if arguments.character_command == "benchmark-run":
        return await _run_benchmark(
            arguments,
            write_json=write_json,
            load_creation_brief=load_creation_brief,
            container_factory=container_factory,
        )
    if arguments.character_command == "import-image":
        brief = load_creation_brief(arguments.brief)
        pack = await container.character_design_service.import_candidate(
            brief,
            arguments.image,
            output_prefix=arguments.output_prefix,
            run_id=arguments.run_id,
        )
        print(write_json(arguments.manifest, pack.to_dict()))
        return 0
    if arguments.character_command == "create":
        brief = load_creation_brief(arguments.brief)
        pack = await container.character_design_service.generate_candidates(
            brief,
            count=arguments.count,
            output_prefix=arguments.output_prefix,
            run_id=arguments.run_id,
            style_reference_path=arguments.style_reference,
            style_weight=arguments.style_weight,
        )
        print(write_json(arguments.manifest, pack.to_dict()))
        return 0
    if arguments.character_command == "approve-design":
        from core.domain.value_objects.character_design import CharacterDesignCandidate

        brief = load_creation_brief(arguments.brief)
        manifest = _load_object(arguments.manifest)
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
                item for item in raw_candidates
                if isinstance(item, dict)
                and item.get("storage_key") == arguments.candidate_key
            ),
            None,
        )
        if selected is None:
            raise ValueError("Selected design candidate is not present in the manifest.")
        approval = await container.character_canonical_approval_service.approve_candidate(
            brief,
            CharacterDesignCandidate.from_dict(selected),
            approved_by=arguments.approved_by,
            character_version=arguments.version,
            output_prefix=arguments.output_prefix,
            brief_consistency_confirmed=bool(arguments.confirm_brief_consistency),
        )
        print(write_json(arguments.output, approval.to_dict()))
        return 0
    if arguments.character_command == "turnaround-tournament":
        return await _run_turnaround_tournament(
            arguments,
            container=container,
            write_json=write_json,
            load_creation_brief=load_creation_brief,
        )
    if arguments.character_command == "turnaround":
        from core.domain.value_objects.character_design import CharacterCanonicalApproval

        brief = load_creation_brief(arguments.brief)
        approval_payload = _load_object(arguments.approval)
        if arguments.restore_superseded:
            if not arguments.restored_by:
                raise ValueError(
                    "--restore-superseded requires --restored-by: restoring a "
                    "superseded render is a human verdict and has to be "
                    "attributed."
                )
            restored_pack = (
                await container.character_view_pack_generation_service.restore_superseded_views(
                    brief,
                    CharacterCanonicalApproval.from_dict(approval_payload),
                    views=getattr(arguments, "rerender_views", None) or (),
                    restored_by=arguments.restored_by,
                    reason=arguments.reason or "",
                    output_prefix=arguments.output_prefix,
                )
            )
            print(write_json(arguments.manifest, restored_pack.to_dict()))
            return 0
        view_pack = await container.character_view_pack_generation_service.generate_canonical_views(
            brief,
            CharacterCanonicalApproval.from_dict(approval_payload),
            output_prefix=arguments.output_prefix,
            view_candidate_count=getattr(arguments, "seeds", None) or None,
            rerender_views=getattr(arguments, "rerender_views", None) or None,
        )
        print(write_json(arguments.manifest, view_pack.to_dict()))
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
            print(write_json(arguments.output, payload))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if arguments.character_command == "reject-view-pack":
        raw_version = str(arguments.version).strip().casefold().removeprefix("v")
        rejection = await container.character_view_pack_generation_service.reject_view_pack(
            character_id=arguments.character,
            character_version=int(raw_version),
            rejected_by=arguments.rejected_by,
            reason=arguments.reason,
            output_prefix=arguments.output_prefix,
            superseded_by_version=arguments.superseded_by_version,
        )
        payload = rejection.to_dict()
        if arguments.output:
            print(write_json(arguments.output, payload))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    character = load_character_bible(arguments.input)
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
        from core.domain.value_objects.character_onboarding import CharacterPilotApproval

        pilot_approval = None
        if arguments.pilot_approval:
            pilot_approval = CharacterPilotApproval.from_dict(
                _load_object(arguments.pilot_approval)
            )
        pose_references = None
        if arguments.pose_references:
            raw_references = _load_object(arguments.pose_references)
            if not all(
                isinstance(view, str) and isinstance(storage_key, str)
                for view, storage_key in raw_references.items()
            ):
                raise TypeError("Pose references must map view names to storage keys.")
            pose_references = raw_references
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
        print(
            write_json(
                arguments.manifest,
                {
                    **reference_pack.to_dict(),
                    "automatic_review_deferred": arguments.defer_visual_review,
                    "pack_complete": len(reference_pack.candidates) == 23,
                    "seed_offset": arguments.seed_offset,
                },
            )
        )
        return 0
    if arguments.character_command == "approve-pilot":
        checks = {
            name: bool(getattr(arguments, name))
            for name in (
                "face_match", "hair_match", "immutable_marks_match",
                "outfit_match", "framing_match", "anatomy_pass",
            )
        }
        pilot_approval = await service.approve_pilot(
            character,
            anchor_storage_key=arguments.approved_anchor_key,
            pilot_storage_key=arguments.pilot_key,
            approved_by=arguments.approved_by,
            checks=checks,
        )
        print(write_json(arguments.output, pilot_approval.to_dict()))
        return 0
    if arguments.character_command == "approve-references":
        from dataclasses import replace

        from core.domain.services.character_bible_validation_service import (
            CharacterBibleValidationService,
        )
        from core.domain.value_objects.character_identity import ReferenceView

        selection_payload = _load_object(arguments.selections)
        if not isinstance(selection_payload.get("views"), dict):
            raise TypeError("Reference selections must contain a views object.")
        selected = {
            ReferenceView(str(view)): str(storage_key)
            for view, storage_key in selection_payload["views"].items()
        }
        character = await service.approve_reference_pack(character, selected)
        if arguments.lock_narrative:
            if character.narrative_profile is None:
                raise ValueError("Character has no narrative profile to lock.")
            character.narrative_profile = replace(
                character.narrative_profile, locked=True
            )
        if not CharacterBibleValidationService().validate(character).is_complete:
            raise ValueError("Approved references unexpectedly became invalid.")
        print(
            write_json(
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
    raise ValueError(f"Unsupported character generation command: {arguments.character_command}")


async def _run_pose_pack(
    arguments: argparse.Namespace,
    container: AnimationContainer,
    *,
    write_json: JsonWriter,
    load_creation_brief: BriefLoader,
) -> int:
    from core.application.services.character_pose_pack_batch_service import (
        CharacterPosePackBatchService,
    )
    from core.domain.value_objects.character_design import CharacterCanonicalApproval

    if arguments.pose_pack_command == "generate":
        brief = load_creation_brief(arguments.brief)
        manifest = await container.character_pose_pack_service.generate_pack(
            brief,
            CharacterCanonicalApproval.from_dict(_load_object(arguments.approval)),
            active_series_path=arguments.active_series,
            mode="PRODUCTION",
            output_prefix=arguments.output_prefix,
            run_id=arguments.run_id,
        )
        print(write_json(arguments.manifest, manifest.to_dict()))
        return 0
    if arguments.pose_pack_command == "rerender":
        brief = load_creation_brief(arguments.brief)
        manifest = (
            await container.character_pose_pack_service.rerender_with_changed_guide(
                brief,
                CharacterCanonicalApproval.from_dict(
                    _load_object(arguments.approval)
                ),
                manifest_storage_key=arguments.manifest,
                authorized_by=arguments.authorized_by,
                reason=arguments.reason,
            )
        )
        payload = manifest.to_dict()
        if arguments.output:
            write_json(arguments.output, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if arguments.pose_pack_command == "approve":
        approval = await container.character_pose_pack_service.approve_pack(
            manifest_storage_key=arguments.manifest,
            approved_by=arguments.approved_by,
            confirmed_checks=list(arguments.checks or []),
        )
        print(json.dumps(approval.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if arguments.pose_pack_command == "reject":
        rejection = await container.character_pose_pack_service.reject_pack(
            manifest_storage_key=arguments.manifest,
            rejected_by=arguments.rejected_by,
            reason=arguments.reason,
            superseded_by_version=arguments.superseded_by_version,
        )
        print(json.dumps(rejection.to_dict(), ensure_ascii=False, indent=2))
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


async def _run_turnaround_tournament(
    arguments: argparse.Namespace,
    *,
    container: AnimationContainer,
    write_json: JsonWriter,
    load_creation_brief: BriefLoader,
) -> int:
    """Compare checkpoints on one approved source and print the decision gate."""
    from config.provider_registry import build_flux2_edit_provider
    from config.settings import get_settings
    from core.application.services.character_turnaround_drift_service import (
        CharacterTurnaroundDriftService,
        DriftThresholds,
    )
    from core.application.services.character_turnaround_tournament_service import (
        CharacterTurnaroundTournamentService,
    )
    from infrastructure.providers.keyframe.comfyui_memory_releaser import (
        ComfyUiMemoryReleaser,
    )

    if not 1 <= arguments.seeds <= 6:
        raise ValueError("Turnaround tournament seeds must be between 1 and 6.")
    workspace_root = Path(__file__).resolve().parents[1]
    settings = get_settings()
    brief = load_creation_brief(arguments.brief)
    run_id = arguments.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    storage = container.keyframe_storage

    def provider_factory(model_lock: Any):
        return build_flux2_edit_provider(settings, model_lock, storage=storage)

    service = CharacterTurnaroundTournamentService(
        workspace_root,
        provider_factory,
        drift_service=CharacterTurnaroundDriftService(
            accent_colour=settings.character_drift_accent_colour,
            mark_side=settings.character_drift_mark_side,
        ),
        memory_releaser=ComfyUiMemoryReleaser(settings.comfyui_api_url).release,
    )
    report = await service.run(
        benchmark_path=arguments.benchmark,
        brief=brief,
        storage=storage,
        source_storage_key=arguments.source_storage_key,
        model_lock_paths=arguments.model_locks,
        seeds=[
            arguments.seed_base + index * 101 for index in range(arguments.seeds)
        ],
        run_id=run_id,
        output_prefix=arguments.output_prefix,
        thresholds=(
            DriftThresholds.from_dict(_load_object(arguments.thresholds))
            if arguments.thresholds
            else None
        ),
    )
    print(write_json(arguments.output, report))
    comparison = report["comparison"]
    print(
        json.dumps(
            {
                "verdict": comparison["verdict"],
                "recommended_variant": comparison["recommended_variant"],
                "rationale": comparison["rationale"],
                "universally_flagged_views": comparison[
                    "universally_flagged_views"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


async def _run_benchmark(
    arguments: argparse.Namespace,
    *,
    write_json: JsonWriter,
    load_creation_brief: BriefLoader,
    container_factory: Callable[[], AnimationContainer],
) -> int:
    from config.settings import get_settings
    from core.application.services.character_model_tournament_service import (
        CharacterModelTournamentService,
    )
    from infrastructure.providers.keyframe.comfyui_memory_releaser import (
        ComfyUiMemoryReleaser,
    )

    workspace_root = Path(__file__).resolve().parents[1]
    base_settings = get_settings()
    brief = load_creation_brief(arguments.brief)
    run_id = arguments.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

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
    print(write_json(arguments.output, report))
    return 0


def _load_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"JSON file must contain an object: {path}")
    return payload


__all__ = ["run_character_asset_command"]
