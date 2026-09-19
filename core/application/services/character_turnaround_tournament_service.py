"""Fair source-led turnaround tournament across model locks.

The rent-a-GPU question is not answerable from one successful render. It needs a
comparison in which every variable except the checkpoint is held constant: the
same approved source, the same seeds, the same view order, the same chaining
policy, the same prompt contract, and the same measurement.

This service therefore drives the *shipped* request shape -- it builds requests
through ``CharacterIdentityPromptService.build_reference_request`` and chains
views through ``turnaround_view_policy`` -- so a variant that wins here is a
variant that would actually ship, not a variant that wins a private benchmark.

It refuses to compare engines that implement different edit contracts, and it
records the decision gate explicitly so the local-vs-rented call is a reading of
the report rather than a memory of a conversation.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from core.application.services.character_identity_prompt_service import (
    CharacterIdentityPromptService,
)
from core.application.services.character_quality_benchmark_service import (
    CharacterQualityBenchmarkService,
)
from core.application.services.character_turnaround_drift_service import (
    CharacterTurnaroundDriftService,
    DriftThresholds,
)
from core.application.services.model_lock_service import load_model_lock
from core.domain.services.turnaround_view_policy import (
    edit_turnaround_dependencies,
    edit_turnaround_order,
)
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from core.domain.value_objects.production_infra import ModelLock

ConditioningReference = tuple[str, str, str, float]


class EditTurnaroundProvider(Protocol):
    """The slice of ``KeyframeGenerationPort`` this tournament drives."""

    @property
    def name(self) -> str: ...

    @property
    def edit_contract(self) -> str: ...

    async def generate_keyframe(
        self, request: KeyframeGenerationRequest
    ) -> Any: ...


class _WritableStorage(Protocol):
    async def load(self, key: str) -> bytes: ...

    async def save(self, key: str, data: bytes, content_type: str) -> Any: ...


@dataclass(frozen=True)
class _SeedRender:
    seed: int
    storage_key: str
    content_hash: str
    drift: dict[str, Any]

    @property
    def score(self) -> tuple[int, float]:
        """Fewer drift reasons first, then less palette movement."""
        return (
            len(self.drift["reasons"]),
            float(self.drift["metrics"]["palette_distance"]),
        )


class CharacterTurnaroundTournamentService:
    """Render one approved source through several checkpoints and compare."""

    def __init__(
        self,
        workspace_root: str | Path,
        provider_factory: Callable[[ModelLock], EditTurnaroundProvider],
        *,
        drift_service: CharacterTurnaroundDriftService,
        prompt_service: CharacterIdentityPromptService | None = None,
        memory_releaser: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._provider_factory = provider_factory
        self._drift_service = drift_service
        self._prompt_service = prompt_service or CharacterIdentityPromptService()
        self._memory_releaser = memory_releaser

    async def run(
        self,
        *,
        benchmark_path: str | Path,
        brief: CharacterCreationBrief,
        storage: _WritableStorage,
        source_storage_key: str,
        model_lock_paths: Sequence[str | Path],
        seeds: Sequence[int],
        run_id: str,
        output_prefix: str = "benchmarks/turnaround",
        thresholds: DriftThresholds | None = None,
    ) -> dict[str, Any]:
        clean_run_id = run_id.strip()
        if not clean_run_id or not re.fullmatch(r"[a-zA-Z0-9_-]+", clean_run_id):
            raise ValueError("Turnaround tournament run_id must be one portable path segment.")
        clean_seeds = [int(seed) for seed in seeds]
        if not clean_seeds:
            raise ValueError("Turnaround tournament requires at least one seed.")
        if len(set(clean_seeds)) != len(clean_seeds):
            raise ValueError("Turnaround tournament seeds must be unique.")
        if any(seed < 0 for seed in clean_seeds):
            raise ValueError("Turnaround tournament seeds must not be negative.")
        if len(model_lock_paths) < 2:
            raise ValueError("A turnaround tournament requires at least two model locks.")
        if not source_storage_key.strip():
            raise ValueError("Turnaround tournament requires source_storage_key.")

        benchmark = CharacterQualityBenchmarkService(self._workspace_root).validate(
            benchmark_path
        )
        source_bytes = await storage.load(source_storage_key)
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        reference_asset = (self._workspace_root / benchmark.reference_asset).resolve()
        reference_sha256 = hashlib.sha256(reference_asset.read_bytes()).hexdigest()
        if source_sha256 != reference_sha256:
            raise ValueError(
                "Tournament source does not match the benchmark reference; "
                "scoring one character's turnaround with another's benchmark "
                "would be meaningless."
            )

        variants = self._prepare_variants(model_lock_paths)
        order = edit_turnaround_order()
        band = thresholds or DriftThresholds()
        results: list[dict[str, Any]] = []
        for lock_path, lock, slug in variants:
            if self._memory_releaser is not None:
                await self._memory_releaser()
            results.append(
                await self._run_variant(
                    lock_path=lock_path,
                    lock=lock,
                    slug=slug,
                    brief=brief,
                    storage=storage,
                    source_bytes=source_bytes,
                    source_storage_key=source_storage_key,
                    source_sha256=source_sha256,
                    order=order,
                    seeds=clean_seeds,
                    run_id=clean_run_id,
                    output_prefix=output_prefix,
                    band=band,
                )
            )
            if self._memory_releaser is not None:
                await self._memory_releaser()

        return {
            "schema_version": 1,
            "report_type": "character_turnaround_tournament",
            "status": "PENDING_HUMAN_REVIEW",
            "tournament_id": clean_run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "benchmark_id": benchmark.benchmark_id,
            "benchmark_reference_sha256": benchmark.reference_sha256,
            "brief_hash": brief.content_hash,
            "character_id": brief.character_id,
            "source_storage_key": source_storage_key,
            "source_sha256": source_sha256,
            "prompt_contract": results[0]["edit_contract"],
            "view_order": list(order),
            "seeds": clean_seeds,
            "shared_dependencies": results[0]["shared_dependencies"],
            "thresholds": band.to_dict(),
            "human_criteria": [item.to_dict() for item in benchmark.human_criteria],
            "prohibited_transfer": list(benchmark.prohibited_transfer),
            "variants": results,
            "comparison": self._compare(results, order),
        }

    # ------------------------------------------------------------------
    # Preparation
    # ------------------------------------------------------------------
    def _prepare_variants(
        self, model_lock_paths: Sequence[str | Path]
    ) -> list[tuple[Path, ModelLock, str]]:
        """Load every lock and prove the comparison is fair before rendering."""
        variants: list[tuple[Path, ModelLock, str]] = []
        checkpoint_hashes: set[str] = set()
        dependency_fingerprint: dict[str, str] | None = None
        for raw_path in model_lock_paths:
            lock_path = Path(raw_path).resolve()
            lock_path.relative_to(self._workspace_root)
            lock = load_model_lock(lock_path)
            checkpoint = lock.entry("diffusion_model")
            if checkpoint.sha256 in checkpoint_hashes:
                raise ValueError(
                    "Turnaround tournament model locks contain a duplicate checkpoint."
                )
            checkpoint_hashes.add(checkpoint.sha256)
            current = {
                entry.role: entry.sha256
                for entry in lock.entries
                if entry.role != "diffusion_model"
            }
            if dependency_fingerprint is None:
                dependency_fingerprint = current
            elif current != dependency_fingerprint:
                raise ValueError(
                    "Tournament model locks must use identical non-checkpoint "
                    "dependencies, otherwise the comparison is not about the model."
                )
            slug = re.sub(
                r"[^a-z0-9]+", "-", Path(checkpoint.filename).stem.casefold()
            ).strip("-")
            variants.append((lock_path, lock, slug))
        return variants

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    async def _run_variant(
        self,
        *,
        lock_path: Path,
        lock: ModelLock,
        slug: str,
        brief: CharacterCreationBrief,
        storage: _WritableStorage,
        source_bytes: bytes,
        source_storage_key: str,
        source_sha256: str,
        order: tuple[str, ...],
        seeds: Sequence[int],
        run_id: str,
        output_prefix: str,
        band: DriftThresholds,
    ) -> dict[str, Any]:
        provider = self._provider_factory(lock)
        contract = str(getattr(provider, "edit_contract", ""))
        if not contract:
            raise ValueError(
                f"Provider {provider.name!r} does not declare a source-led edit "
                "contract and cannot enter a turnaround tournament."
            )
        root = f"{output_prefix.strip('/')}/{run_id}/{slug}"
        source_reference: ConditioningReference = (
            "FRONT",
            source_storage_key,
            source_sha256,
            1.0,
        )
        # view -> candidate key -> render
        renders: dict[str, list[_SeedRender]] = {view: [] for view in order}
        for seed in seeds:
            produced: dict[str, ConditioningReference] = {"FRONT": source_reference}
            for view in order:
                dependencies = edit_turnaround_dependencies(view)
                references = (
                    source_reference,
                    *(
                        produced[name]
                        for name in dependencies
                        if name != "FRONT"
                    ),
                )
                request = self._prompt_service.build_reference_request(
                    brief,
                    view=view,
                    direction=view,
                    seed=seed,
                    references=references,
                )
                generated = await provider.generate_keyframe(request)
                image_bytes = generated.image_bytes
                digest = hashlib.sha256(image_bytes).hexdigest()
                key = f"{root}/candidates/{view.casefold().replace('_', '-')}-s{seed}.png"
                await storage.save(key, image_bytes, "image/png")
                drift = self._drift_service.evaluate(
                    source_bytes=source_bytes,
                    views={view: image_bytes},
                    thresholds=band,
                )["views"][0]
                renders[view].append(
                    _SeedRender(
                        seed=seed,
                        storage_key=key,
                        content_hash=digest,
                        drift=drift,
                    )
                )
                produced[view] = (view, key, digest, 1.0)

        chosen: dict[str, dict[str, Any]] = {}
        for view, candidates in renders.items():
            winner = min(candidates, key=lambda item: item.score)
            accepted_key = f"{root}/{view.casefold().replace('_', '-')}.png"
            await storage.save(
                accepted_key,
                await storage.load(winner.storage_key),
                "image/png",
            )
            chosen[view] = {
                "view": view,
                "storage_key": accepted_key,
                "content_hash": winner.content_hash,
                "seed": winner.seed,
                "status": winner.drift["status"],
                "reasons": list(winner.drift["reasons"]),
                "metrics": winner.drift["metrics"],
                "candidates": [
                    {
                        "seed": item.seed,
                        "storage_key": item.storage_key,
                        "status": item.drift["status"],
                        "reasons": list(item.drift["reasons"]),
                        "palette_distance": item.drift["metrics"]["palette_distance"],
                        "head_accent_ratio": item.drift["metrics"]["head_accent_ratio"],
                    }
                    for item in sorted(candidates, key=lambda item: item.seed)
                ],
            }

        flagged = [view for view, item in chosen.items() if item["reasons"]]
        checkpoint = lock.entry("diffusion_model")
        return {
            "variant_id": slug,
            "provider": provider.name,
            "edit_contract": contract,
            "checkpoint": checkpoint.filename,
            "checkpoint_sha256": checkpoint.sha256,
            "checkpoint_size_bytes": checkpoint.size_bytes,
            "model_lock": lock_path.relative_to(self._workspace_root).as_posix(),
            "shared_dependencies": {
                entry.role: entry.sha256
                for entry in lock.entries
                if entry.role != "diffusion_model"
            },
            "views": [chosen[view] for view in order],
            "flagged_views": flagged,
            "flagged_view_count": len(flagged),
        }

    # ------------------------------------------------------------------
    # Decision gate
    # ------------------------------------------------------------------
    @staticmethod
    def _compare(
        results: list[dict[str, Any]], order: tuple[str, ...]
    ) -> dict[str, Any]:
        per_view: dict[str, dict[str, Any]] = {}
        for view in order:
            flagged_by = [
                item["variant_id"] for item in results if view in item["flagged_views"]
            ]
            per_view[view] = {
                "flagged_by_variants": flagged_by,
                "flagged_by_every_variant": len(flagged_by) == len(results),
            }
        universally_flagged = [
            view for view, item in per_view.items() if item["flagged_by_every_variant"]
        ]
        clean_variants = [
            item for item in results if item["flagged_view_count"] == 0
        ]
        ranked = sorted(
            results,
            key=lambda item: (
                item["flagged_view_count"],
                sum(
                    float(view["metrics"]["palette_distance"])
                    for view in item["views"]
                ),
            ),
        )
        if clean_variants:
            # A checkpoint that already passes everywhere leaves nothing for a
            # bigger GPU to fix, so recommend the smallest one that passes.
            verdict = "LOCAL_SUFFICIENT"
            recommended = min(
                clean_variants, key=lambda item: item["checkpoint_size_bytes"]
            )["variant_id"]
            rationale = (
                "At least one variant placed every view inside tolerance, so the "
                "remaining work is prompt and QC, not compute."
            )
        elif universally_flagged:
            verdict = "ESCALATE_TO_LARGER_MODEL"
            recommended = ranked[0]["variant_id"]
            rationale = (
                "These views drifted in every variant: "
                + ", ".join(universally_flagged)
                + ". The defect is not specific to one checkpoint."
            )
        else:
            verdict = "INCONCLUSIVE"
            recommended = ranked[0]["variant_id"]
            rationale = (
                "Different variants failed on different views; widen the seed "
                "sweep before spending on hardware."
            )
        return {
            "best_variant_by_drift": ranked[0]["variant_id"],
            "recommended_variant": recommended,
            "verdict": verdict,
            "rationale": rationale,
            "per_view": per_view,
            "universally_flagged_views": universally_flagged,
            "gate_policy": (
                "Locally clean views mean the local engine is sufficient. A view "
                "that drifts in every variant is a method or prompt problem, and "
                "renting a GPU will not fix it. Renting is only justified when "
                "the failing views are model-capacity dependent."
            ),
            "human_review_required": True,
        }


__all__ = ["CharacterTurnaroundTournamentService", "EditTurnaroundProvider"]
