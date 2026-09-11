"""Fair, identity-safe checkpoint tournament for character design candidates."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from core.application.services.character_quality_benchmark_service import (
    CharacterQualityBenchmarkService,
)
from core.application.services.model_lock_service import load_model_lock
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief


class CharacterCandidateGenerator(Protocol):
    async def generate_candidates(self, brief: CharacterCreationBrief, **kwargs: Any) -> Any: ...


class CharacterModelTournamentService:
    """Generate equal text-only candidate packs without leaking benchmark identity."""

    def __init__(
        self,
        workspace_root: str | Path,
        generator_factory: Callable[[Path], CharacterCandidateGenerator],
        memory_releaser: Callable[[], Awaitable[None]],
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._generator_factory = generator_factory
        self._memory_releaser = memory_releaser

    async def run(
        self,
        *,
        benchmark_path: str | Path,
        brief: CharacterCreationBrief,
        model_lock_paths: Sequence[str | Path],
        count: int,
        run_id: str,
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
        self._validate_brief_compatibility(benchmark.visual_targets, brief)
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
            await self._memory_releaser()
            checkpoint = lock.entry("checkpoint")
            generator = self._generator_factory(lock_path)
            pack = await generator.generate_candidates(
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
            await self._memory_releaser()

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
    def _validate_brief_compatibility(
        visual_targets: Sequence[str], brief: CharacterCreationBrief
    ) -> None:
        """Reject contradictory benchmark inputs before loading large checkpoints."""
        targets = " ".join(visual_targets).casefold().replace("-", " ")
        avoided = {item.casefold().replace("-", " ") for item in brief.avoid}
        requires_full_body = "full body" in targets or "head to boots" in targets
        forbids_full_body = any(
            value in avoided for value in ("full body", "legs", "feet")
        )
        if requires_full_body and (
            brief.style_preset.casefold() == "selma-anime-v3-face"
            or forbids_full_body
        ):
            raise ValueError(
                "Benchmark requires a full-body character, but the brief is a "
                "face/crop brief or explicitly forbids full-body anatomy."
            )
