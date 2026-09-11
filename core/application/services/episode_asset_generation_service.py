"""Opt-in episode asset generation orchestration.

The director remains usable offline and without production wiring.  This service
is only used when an operator explicitly asks ``episode prepare`` to dispatch
asset generation; it reuses the existing pose-pack batch and background
factory services and reports failures without pretending that an asset exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.application.services.background_factory_service import (
    BackgroundFactoryService,
)
from core.application.services.character_pose_pack_batch_service import (
    CharacterPosePackBatchService,
)
from core.application.services.character_pose_pack_service import (
    CharacterPosePackService,
)
from core.application.services.series_style_lock_service import SeriesStyleLockService
from core.domain.entities.location_bible import LocationBible
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.background_production import BackgroundCandidatePack
from core.domain.value_objects.character_pose_pack import CharacterPosePackManifest
from core.domain.value_objects.episode_director_plan import EpisodeDirectorPlan


@dataclass(frozen=True)
class EpisodeAssetGenerationResult:
    pose_packs: Mapping[str, CharacterPosePackManifest]
    background_packs: Mapping[str, BackgroundCandidatePack]
    failures: Mapping[str, str]
    artifacts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "FAILED" if self.failures else "COMPLETED",
            "pose_pack_count": len(self.pose_packs),
            "background_pack_count": len(self.background_packs),
            "failures": dict(self.failures),
            "artifacts": list(self.artifacts),
        }


class EpisodeAssetGenerationService:
    """Dispatch the already-existing asset factories for one episode."""

    def __init__(
        self,
        pose_pack_service: CharacterPosePackService,
        background_factory_service: BackgroundFactoryService,
        storage: StoragePort,
        *,
        style_lock_resolver: SeriesStyleLockService | None = None,
    ) -> None:
        self._pose_pack_service = pose_pack_service
        self._background_factory_service = background_factory_service
        self._storage = storage
        self._style_lock_resolver = style_lock_resolver

    async def generate(
        self,
        plan: EpisodeDirectorPlan,
        *,
        locations: tuple[LocationBible, ...] = (),
        pose_jobs: list[dict[str, Any]] | None = None,
        output_root: str | Path = "output/episodes/assets",
        asset_mode: str = "DISCOVERY",
        active_series_path: str | Path | None = None,
        workflow_path: str | Path | None = None,
    ) -> EpisodeAssetGenerationResult:
        if asset_mode not in {"DISCOVERY", "PRODUCTION"}:
            raise ValueError("Episode asset mode must be DISCOVERY or PRODUCTION.")
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=True)
        pose_packs: dict[str, CharacterPosePackManifest] = {}
        background_packs: dict[str, BackgroundCandidatePack] = {}
        failures: dict[str, str] = {}
        artifacts: list[str] = []

        if pose_jobs:
            batch_path = root / "pose-pack-batch.json"
            try:
                batch = await CharacterPosePackBatchService(
                    self._pose_pack_service,
                    style_lock_resolver=(
                        self._style_lock_resolver
                        if asset_mode == "PRODUCTION"
                        else None
                    ),
                ).run(
                    pose_jobs,
                    output_manifest=batch_path,
                    continue_on_error=True,
                    active_series_path=(
                        active_series_path if asset_mode == "PRODUCTION" else None
                    ),
                    workflow_path=(
                        workflow_path if asset_mode == "PRODUCTION" else None
                    ),
                )
                artifacts.append(str(batch_path))
                for item in batch.get("characters", []):
                    if not isinstance(item, Mapping):
                        continue
                    character_id = str(item.get("character_id", "")).strip()
                    manifest_key = str(item.get("manifest_storage_key", "")).strip()
                    if item.get("status") == "FAILED":
                        failures[f"pose-pack-{character_id}"] = str(
                            item.get("error", "Pose-pack generation failed.")
                        )
                        continue
                    if not manifest_key:
                        failures[f"pose-pack-{character_id}"] = (
                            "Pose-pack generation returned no manifest reference."
                        )
                        continue
                    try:
                        raw = json.loads(
                            (await self._storage.load(manifest_key)).decode("utf-8")
                        )
                        manifest = CharacterPosePackManifest.from_dict(raw)
                    except Exception as error:  # noqa: BLE001 - per-job reporting
                        failures[f"pose-pack-{character_id}"] = str(error)
                        continue
                    if manifest.character_id != character_id:
                        failures[f"pose-pack-{character_id}"] = (
                            "Pose-pack manifest belongs to a different character."
                        )
                        continue
                    pose_packs[manifest.character_id] = manifest
                    copy_path = root / "pose-packs" / f"{manifest.character_id}.json"
                    copy_path.parent.mkdir(parents=True, exist_ok=True)
                    copy_path.write_text(
                        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2)
                        + "\n",
                        encoding="utf-8",
                    )
                    artifacts.append(str(copy_path))
            except Exception as error:  # noqa: BLE001 - episode boundary
                for job in pose_jobs:
                    character_id = str(job.get("character_id", "")).strip()
                    if character_id:
                        failures[f"pose-pack-{character_id}"] = str(error)

        required_locations = {
            item.location_id for item in plan.background_requirements
        }
        supplied_location_ids = {location.location_id for location in locations}
        for location_id in sorted(required_locations - supplied_location_ids):
            failures[f"background-pack-{location_id}"] = (
                "Location Bible is required before background generation can be dispatched."
            )
        for location in locations:
            if location.location_id not in required_locations:
                continue
            job_id = f"background-pack-{location.location_id}"
            try:
                pack = await self._background_factory_service.generate(
                    location,
                    evaluate=asset_mode == "PRODUCTION",
                )
                if pack.location_id != location.location_id:
                    failures[job_id] = (
                        "Background candidate pack belongs to a different location."
                    )
                    continue
                background_packs[location.location_id] = pack
                manifest_path = (
                    root / "background-packs" / f"{location.location_id}.json"
                )
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                manifest_path.write_text(
                    json.dumps(pack.to_dict(), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                artifacts.append(str(manifest_path))
            except Exception as error:  # noqa: BLE001 - per-location reporting
                failures[job_id] = str(error)

        return EpisodeAssetGenerationResult(
            pose_packs=pose_packs,
            background_packs=background_packs,
            failures=failures,
            artifacts=tuple(artifacts),
        )
