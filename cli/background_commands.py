"""CLI handlers for location and background asset commands."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from config.container import AnimationContainer

JsonWriter = Callable[[str | Path, dict[str, Any]], Path]


def run_background_command(
    arguments: argparse.Namespace,
    *,
    write_json: JsonWriter,
    container_factory: Callable[[], AnimationContainer],
) -> int:
    if arguments.background_command == "init":
        _initialize_background(arguments, write_json=write_json)
        return 0
    if arguments.background_command == "plan":
        _plan_background(arguments, write_json=write_json)
        return 0
    if arguments.background_command == "approve":
        _approve_backgrounds(arguments, write_json=write_json)
        return 0
    return _generate_backgrounds(
        arguments,
        container=container_factory(),
        write_json=write_json,
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


def _initialize_background(arguments: argparse.Namespace, *, write_json: JsonWriter) -> None:
    from core.application.services.location_bible_factory_service import (
        LocationBibleFactoryService,
    )

    brief = json.loads(Path(arguments.brief).read_text(encoding="utf-8"))
    if not isinstance(brief, dict):
        raise TypeError("Location brief JSON must contain an object.")
    location = LocationBibleFactoryService().create(brief)
    print(
        write_json(
            arguments.output,
            {"schema_version": 1, "location_bible": location.to_dict()},
        )
    )


def _plan_background(arguments: argparse.Namespace, *, write_json: JsonWriter) -> None:
    from core.application.services.background_factory_service import (
        BackgroundFactoryService,
    )

    plan = BackgroundFactoryService.plan(_load_location_bible(arguments.input))
    print(write_json(arguments.output, plan.to_dict()))


def _generate_backgrounds(
    arguments: argparse.Namespace,
    *,
    container: AnimationContainer,
    write_json: JsonWriter,
) -> int:
    import asyncio

    pack = asyncio.run(
        container.background_factory_service.generate(
            _load_location_bible(arguments.input),
            output_prefix=arguments.output_prefix,
        )
    )
    print(write_json(arguments.manifest, pack.to_dict()))
    return 0


def _approve_backgrounds(arguments: argparse.Namespace, *, write_json: JsonWriter) -> None:
    from core.application.services.asset_approval_service import AssetApprovalService
    from core.domain.value_objects.background_production import (
        BackgroundCandidate,
        BackgroundCandidatePack,
    )

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
    candidate_pack = BackgroundCandidatePack(
        location_id=location.location_id,
        candidates=tuple(
            BackgroundCandidate(
                recipe_id=str(item.get("recipe_id", "")),
                storage_key=str(item.get("storage_key", "")),
                width=int(item.get("width", 0)),
                height=int(item.get("height", 0)),
                attempt=int(item.get("attempt", 1)),
                content_hash=str(item.get("content_hash", "")),
            )
            for item in candidates
        ),
        quarantined=(),
    )
    receipt = None
    try:
        receipt = AssetApprovalService.receipt(
            asset_id=location.location_id,
            asset_hash=AssetApprovalService.asset_set_digest(
                [candidate.content_hash for candidate in candidate_pack.candidates]
            ),
            manifest_payload=candidate_pack.to_dict(),
            approved_by=arguments.approved_by,
        ).to_dict()
    except Exception:
        receipt = None
    print(
        write_json(
            arguments.output,
            {
                "schema_version": 1,
                "approval": {
                    "approved_by": arguments.approved_by,
                    "background_pack_approved": receipt is not None,
                    "approved_storage_keys": keys,
                },
                "location_bible": locked.to_dict(),
                "candidates": candidates,
                "quarantined": [],
                "approval_receipt": receipt,
                "human_approved": receipt is not None,
            },
        )
    )


__all__ = ["run_background_command"]
