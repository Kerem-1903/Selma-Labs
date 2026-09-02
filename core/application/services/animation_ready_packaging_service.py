from __future__ import annotations

import json

from core.domain.entities.animatic_project import AnimaticProject, AnimaticStatus
from core.domain.entities.animation_ready_package import (
    AnimationReadyPackage,
    ShotPackageSources,
)
from core.domain.entities.character_golden_set import CharacterGoldenSet
from core.domain.entities.episode_production_plan import (
    DirectedShot,
    EpisodeProductionPlan,
)
from core.domain.exceptions import AnimationPackageError
from core.domain.ports.storage_port import StoragePort


class AnimationReadyPackagingService:
    def __init__(self, storage: StoragePort) -> None:
        self._storage = storage

    async def package_episode(
        self,
        *,
        plan: EpisodeProductionPlan,
        animatic: AnimaticProject,
        golden_set: CharacterGoldenSet,
        sources: dict[str, ShotPackageSources],
        package_prefix: str = "packages",
    ) -> tuple[AnimationReadyPackage, ...]:
        if animatic.status is not AnimaticStatus.LOCKED:
            raise AnimationPackageError(
                "Animation packaging requires a locked animatic."
            )
        if animatic.production_plan_id != plan.id:
            raise AnimationPackageError(
                "Animatic does not belong to the production plan."
            )
        planned_shots = tuple(directed.plan.id for directed in plan.shots)
        animatic_shots = tuple(clip.shot_id for clip in animatic.clips)
        if animatic_shots != planned_shots:
            raise AnimationPackageError(
                "Animatic shot order does not match the production plan."
            )
        if not golden_set.locked:
            raise AnimationPackageError(
                "Animation packaging requires a locked Golden Set."
            )
        if any(
            directed.plan.character_state.character_id != golden_set.character_id
            for directed in plan.shots
        ):
            raise AnimationPackageError(
                "Golden Set does not match every shot character."
            )
        packages = []
        for directed in plan.shots:
            shot_sources = sources.get(directed.plan.id)
            if shot_sources is None:
                raise AnimationPackageError(
                    f"Animation sources for '{directed.plan.id}' are missing."
                )
            for key in shot_sources.all_keys:
                if not await self._storage.exists(key):
                    raise AnimationPackageError(
                        f"Required animation asset '{key}' is missing."
                    )
            package = AnimationReadyPackage.create(
                shot_id=directed.plan.id,
                package_root=f"{package_prefix.rstrip('/')}/{directed.plan.id}",
            )
            await self._materialize(package, directed, shot_sources, golden_set)
            packages.append(package)
        return tuple(packages)

    async def _materialize(
        self,
        package: AnimationReadyPackage,
        directed: DirectedShot,
        sources: ShotPackageSources,
        golden_set: CharacterGoldenSet,
    ) -> None:
        copies = (
            (sources.start_keyframe, package.start_keyframe_key, "image/png"),
            (sources.end_keyframe, package.end_keyframe_key, "image/png"),
            (sources.background_clean, package.background_clean_key, "image/png"),
            (sources.character_mask, package.character_mask_key, "image/png"),
            (sources.dialogue_audio, package.dialogue_audio_key, "audio/wav"),
        )
        for source, destination, content_type in copies:
            await self._storage.save(
                destination, await self._storage.load(source), content_type
            )
        contract = {
            "schema_version": 1,
            "shot": directed.to_dict(),
            "golden_set_id": golden_set.id,
            "golden_model": {
                "id": golden_set.model_id,
                "revision": golden_set.model_revision,
            },
            "render": {
                "width": 1920,
                "height": 1080,
                "fps": 24,
                "duration_seconds": directed.plan.duration_seconds,
            },
        }
        effects = {
            "schema_version": 1,
            "shot_id": directed.plan.id,
            "effects": [
                {"type": effect, "intensity": "controlled"}
                for effect in directed.effects
            ],
        }
        await self._storage.save(
            package.shot_contract_key,
            json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True).encode(),
            "application/json",
        )
        await self._storage.save(
            package.effects_spec_key,
            json.dumps(effects, ensure_ascii=False, indent=2, sort_keys=True).encode(),
            "application/json",
        )
