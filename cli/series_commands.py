"""CLI handlers for series project and style-lock commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


async def _run_smoke_production_lock(arguments: argparse.Namespace) -> int:
    """Render one frame through the locked dialect to earn a lock receipt.

    The receipt is produced here rather than typed by hand: a hand-authored
    receipt would prove nothing about the pipeline and would silently defeat
    the fail-closed intent of ``mark-production-compatible``.
    """
    from config.container import create_container
    from config.settings import get_settings
    from core.application.services.style_lock_smoke_service import (
        DEFAULT_SEED,
        StyleLockSmokeService,
    )

    workspace_root = Path(__file__).resolve().parents[1]
    container = create_container(settings=get_settings())
    service = StyleLockSmokeService(
        workspace_root,
        generator=container.keyframe_generation_provider,
        full_model_hash=bool(arguments.full_model_hash),
        seed=DEFAULT_SEED if arguments.seed is None else arguments.seed,
    )
    receipt_path = Path(arguments.receipt)
    image_path = (
        Path(arguments.image) if arguments.image else receipt_path.with_suffix(".png")
    )
    receipt = await service.run(
        arguments.project,
        workflow_path=arguments.workflow,
        receipt_path=receipt_path,
        image_path=image_path,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


def run_series_command(arguments: argparse.Namespace) -> int:
    from core.application.services.series_project_service import SeriesProjectService
    from core.application.services.series_style_lock_service import (
        SeriesStyleLockService,
    )

    workspace_root = Path(__file__).resolve().parents[1]
    service = SeriesProjectService(workspace_root)
    if arguments.series_command == "approve-style":
        checks = tuple(arguments.checks or ("creative-style-reviewed",))
        receipt = SeriesStyleLockService(workspace_root).write_style_approval(
            arguments.project,
            approved_by=arguments.approved_by,
            approval_criteria=checks,
        )
        print(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if arguments.series_command == "promote-style":
        receipt = SeriesStyleLockService(workspace_root).promote_style(
            arguments.project
        )
        print(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if arguments.series_command == "create-production-lock":
        lock = SeriesStyleLockService(workspace_root).write_production_lock(
            arguments.project,
            workflow_path=arguments.workflow,
            style_approval_receipt_sha256=arguments.receipt_sha256,
            width=arguments.width,
            height=arguments.height,
            sampler=arguments.sampler,
            steps=arguments.steps,
            cfg=arguments.cfg,
            denoise=arguments.denoise,
            lock_version=arguments.lock_version,
        )
        print(json.dumps(lock.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if arguments.series_command == "smoke-production-lock":
        import asyncio

        return asyncio.run(_run_smoke_production_lock(arguments))
    if arguments.series_command == "mark-production-compatible":
        lock = SeriesStyleLockService(workspace_root).mark_production_compatible(
            arguments.project,
            smoke_test_receipt_path=arguments.smoke_receipt,
        )
        print(json.dumps(lock.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if arguments.series_command == "register-character":
        registry = service.register_character(
            project_path=arguments.project,
            bible_path=arguments.bible,
            role=arguments.role,
            version=arguments.version,
            status=arguments.status,
        )
        print(json.dumps(registry.to_dict(), ensure_ascii=False, indent=2))
        return 0

    project, registry = service.load(arguments.project)
    try:
        snapshot = SeriesStyleLockService(workspace_root).resolve_production(
            arguments.project,
            workflow_path=workspace_root / "assets/comfyui_keyframe_workflow.json",
        )
    except Exception as error:  # noqa: BLE001 - status reports readiness without hiding it
        style_lock_payload: dict[str, Any] = {
            "status": "BLOCKED",
            "blocking_reason": getattr(error, "reason", "STYLE_LOCK_INVALID"),
            "detail": getattr(error, "detail", str(error)),
        }
    else:
        style_lock_payload = {
            "status": "READY",
            "blocking_reason": "",
            "snapshot": snapshot.to_dict(),
        }
    print(
        json.dumps(
            {
                "status": "VALID",
                "series": project.to_dict(),
                "cast": registry.to_dict(),
                "cast_size": len(registry.members),
                "production_ready": style_lock_payload["status"] == "READY",
                "style_lock": style_lock_payload,
                "next_gate": (
                    "REGISTER_FIRST_CHARACTER"
                    if not registry.members
                    else "VALIDATE_CAST_DISTINCTIVENESS"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


__all__ = ["run_series_command"]
