"""Fair, identity-safe checkpoint tournament for character design candidates."""

from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.container import AnimationContainer
from config.settings import Settings
from core.application.services.character_quality_benchmark_service import (
    CharacterQualityBenchmarkService,
)
from core.application.services.model_lock_service import load_model_lock
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief


class CharacterModelTournamentService:
    """Generate equal text-only candidate packs without leaking benchmark identity."""

    def __init__(
        self,
        workspace_root: str | Path,
        container_factory: Callable[..., AnimationContainer],
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._container_factory = container_factory

    async def run(
        self,
        *,
        benchmark_path: str | Path,
        brief: CharacterCreationBrief,
        model_lock_paths: Sequence[str | Path],
        count: int,
        run_id: str,
        base_settings: Settings,
    ) -> dict[str, Any]:
        if not 1 <= count <= 8:
            raise ValueError("Tournament candidate count must be between 1 and 8.")
        clean_run_id = run_id.strip()
        if not clean_run_id or not re.fullmatch(r"[a-zA-Z0-9_-]+", clean_run_id):
            raise ValueError("Tournament run_id must be one portable path segment.")
        if len(model_lock_paths) < 2:
            raise ValueError("A model tournament requires at least two model locks.")

        benchmark = CharacterQualityBenchmarkService(self._workspace_root).validate(
            benchmark_path
        )
        variants: list[tuple[Path, Any, str]] = []
        checkpoint_hashes: set[str] = set()
        dependency_fingerprint: dict[str, str] | None = None
        for raw_path in model_lock_paths:
            lock_path = Path(raw_path).resolve()
            lock_path.relative_to(self._workspace_root)
            lock = load_model_lock(lock_path)
            checkpoint = lock.entry("checkpoint")
            if checkpoint.sha256 in checkpoint_hashes:
                raise ValueError("Tournament model locks contain a duplicate checkpoint.")
            checkpoint_hashes.add(checkpoint.sha256)
            current_dependencies = {
                entry.role: entry.sha256
                for entry in lock.entries
                if entry.role != "checkpoint"
            }
            if dependency_fingerprint is None:
                dependency_fingerprint = current_dependencies
            elif current_dependencies != dependency_fingerprint:
                raise ValueError(
                    "Tournament model locks must use identical non-checkpoint dependencies."
                )
            slug = re.sub(
                r"[^a-z0-9]+", "-", Path(checkpoint.filename).stem.casefold()
            ).strip("-")
            variants.append((lock_path, lock, slug))

        results: list[dict[str, Any]] = []
        for lock_path, lock, slug in variants:
            await self._release_comfy_memory(base_settings.comfyui_api_url)
            checkpoint = lock.entry("checkpoint")
            settings = base_settings.model_copy(
                update={
                    "keyframe_generation_provider": "comfyui",
                    "comfyui_model_lock_path": str(lock_path),
                    "comfyui_keyframe_checkpoint": "",
                }
            )
            container = self._container_factory(settings=settings)
            pack = await container.character_design_service.generate_candidates(
                brief,
                count=count,
                output_prefix=(
                    f"benchmarks/{benchmark.benchmark_id}/{clean_run_id}/{slug}"
                ),
                run_id="text-only",
            )
            results.append(
                {
                    "variant_id": slug,
                    "checkpoint": checkpoint.filename,
                    "checkpoint_sha256": checkpoint.sha256,
                    "model_lock": lock_path.relative_to(self._workspace_root).as_posix(),
                    "candidate_pack": pack.to_dict(),
                }
            )
            await self._release_comfy_memory(base_settings.comfyui_api_url)

        return {
            "schema_version": 1,
            "status": "PENDING_HUMAN_REVIEW",
            "tournament_id": clean_run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "benchmark_id": benchmark.benchmark_id,
            "benchmark_reference_sha256": benchmark.reference_sha256,
            "benchmark_usage": benchmark.usage,
            "generation_mode": "text_only",
            "identity_reference_used": False,
            "brief_hash": brief.content_hash,
            "character_id": brief.character_id,
            "shared_seed_base": int(brief.content_hash[:8], 16),
            "candidates_per_model": count,
            "human_criteria": [item.to_dict() for item in benchmark.human_criteria],
            "prohibited_transfer": list(benchmark.prohibited_transfer),
            "variants": results,
        }

    @staticmethod
    async def _release_comfy_memory(api_url: str) -> None:
        """Unload the previous checkpoint before a fair low-memory model switch."""

        def release() -> None:
            request = urllib.request.Request(
                f"{api_url.rstrip('/')}/free",
                data=json.dumps(
                    {"unload_models": True, "free_memory": True}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status != 200:
                    raise RuntimeError(
                        f"ComfyUI memory release failed with HTTP {response.status}."
                    )

        await asyncio.to_thread(release)
