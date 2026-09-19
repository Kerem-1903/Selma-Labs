"""Derive the smoke-test receipt that completes a production style lock.

``SeriesStyleLockService.mark_production_compatible`` refuses to enable
production without a receipt proving a successful technical run, but nothing in
the repository produced one. The chain could therefore be created and never
completed, which left ``POSE_PACK``/``keyframe`` production permanently blocked
behind a hand-written artifact -- exactly the kind of invented evidence this
project keeps removing.

This service produces that receipt from a real render instead. It verifies the
lock's own claims first (model-lock bytes, workflow bytes, every weight file),
renders one frame through the locked workflow and sampler settings, and only
then writes the receipt. Every field in the receipt is copied from something
that was observed; none of it is authored by the operator.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.application.services.model_lock_service import load_model_lock
from core.domain.exceptions import StyleLockError
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from core.domain.value_objects.series_project import SeriesProject
from core.domain.value_objects.style_lock import (
    LOCK_COMPATIBLE,
    LOCK_PENDING_SMOKE,
    ProductionStyleLock,
)

#: Deterministic by construction: the receipt claims one specific run, so the
#: same lock must always reproduce the same seed.
DEFAULT_SEED = 20260913

#: A neutral frame exercises checkpoint, text encoder, sampler and VAE with the
#: locked parameters. It deliberately depicts no character: the smoke proves the
#: *pipeline* is executable, not that a character looks right.
SMOKE_PROMPT = (
    "neutral studio reference plate, plain light-gray seamless background, "
    "soft even lighting, single centered simple geometric subject, "
    "clean anime line art, restrained two-step cel shading"
)


@dataclass(frozen=True)
class SmokeRenderEvidence:
    """What the smoke run observed; every field is measured, never supplied."""

    image_bytes: bytes
    width: int
    height: int
    provider: str
    duration_sec: float
    content_hash: str
    provider_asset_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "width": self.width,
            "height": self.height,
            "duration_sec": round(float(self.duration_sec), 3),
            "content_hash": self.content_hash,
            "provider_asset_id": self.provider_asset_id,
        }


class StyleLockSmokeService:
    """Turn one real smoke render into a production-lock completion receipt."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        generator: KeyframeGenerationPort,
        full_model_hash: bool = False,
        seed: int = DEFAULT_SEED,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._generator = generator
        self._full_model_hash = full_model_hash
        self._seed = int(seed)

    # ------------------------------------------------------------------
    # Lock resolution
    # ------------------------------------------------------------------
    def pending_lock(
        self, project_path: str | Path
    ) -> tuple[SeriesProject, ProductionStyleLock]:
        """Load the project and its *pending* production lock."""
        project = self._load_project(project_path)
        lock = self._load_lock(project)
        if lock.compatibility_status == LOCK_COMPATIBLE and lock.production_eligible:
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                "Production style lock is already compatible; a second smoke "
                "receipt would attach evidence to a completed lock.",
            )
        if lock.compatibility_status != LOCK_PENDING_SMOKE:
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                f"Smoke evidence requires a pending lock, not "
                f"'{lock.compatibility_status}'.",
            )
        return project, lock

    def verify_lock_inputs(
        self,
        project: SeriesProject,
        lock: ProductionStyleLock,
        *,
        workflow_path: str | Path,
    ) -> dict[str, Any]:
        """Check the lock still describes the bytes it claims, or fail closed."""
        model_lock_path = self._resolve(project.model_lock)
        model_lock_bytes = self._read(model_lock_path, "model lock")
        actual_model_lock = hashlib.sha256(model_lock_bytes).hexdigest()
        if actual_model_lock != lock.model_lock_sha256:
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                "Model lock bytes no longer match the pending production lock.",
            )
        model_lock = load_model_lock(model_lock_path)

        workflow_file = self._resolve(workflow_path)
        workflow_bytes = self._read(workflow_file, "workflow")
        if workflow_file.name != lock.workflow_id:
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                f"Workflow '{workflow_file.name}' is not the locked workflow "
                f"'{lock.workflow_id}'.",
            )
        actual_workflow = hashlib.sha256(workflow_bytes).hexdigest()
        if actual_workflow != lock.workflow_sha256:
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                "Workflow bytes no longer match the pending production lock.",
            )

        locked_hashes = {entry.role: entry.sha256 for entry in model_lock.entries}
        if locked_hashes != dict(lock.model_hashes):
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED",
                "Model lock entries no longer match the pending production lock.",
            )

        model_root = Path(model_lock.comfyui_root).expanduser()
        roles: dict[str, str] = {}
        for entry in model_lock.entries:
            weight = model_root / entry.relative_path
            if not weight.is_file():
                raise StyleLockError(
                    "STYLE_LOCK_MISSING",
                    f"Locked weight for role '{entry.role}' is missing: {weight}",
                )
            if entry.size_bytes and weight.stat().st_size != entry.size_bytes:
                raise StyleLockError(
                    "STYLE_LOCK_TAMPERED",
                    f"Locked weight for role '{entry.role}' changed size.",
                )
            if self._full_model_hash:
                digest = self._hash_file(weight)
                if digest != entry.sha256:
                    raise StyleLockError(
                        "STYLE_LOCK_TAMPERED",
                        f"Locked weight for role '{entry.role}' changed bytes.",
                    )
                roles[entry.role] = digest
            else:
                roles[entry.role] = "size-match (hash not verified)"

        return {
            "model_lock_sha256": actual_model_lock,
            "workflow_id": workflow_file.name,
            "workflow_sha256": actual_workflow,
            "model_verification": "sha256" if self._full_model_hash else "size",
            "roles": roles,
        }

    # ------------------------------------------------------------------
    # Smoke run
    # ------------------------------------------------------------------
    async def run(
        self,
        project_path: str | Path,
        *,
        workflow_path: str | Path,
        receipt_path: str | Path | None = None,
        image_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Verify the lock, render one frame, and return the receipt payload."""
        project, lock = self.pending_lock(project_path)
        verification = self.verify_lock_inputs(
            project, lock, workflow_path=workflow_path
        )
        evidence = await self._render(lock)
        receipt = self._receipt(project, lock, verification, evidence)
        if receipt_path is not None:
            target = Path(receipt_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
        if image_path is not None:
            frame = Path(image_path)
            frame.parent.mkdir(parents=True, exist_ok=True)
            frame.write_bytes(evidence.image_bytes)
        return receipt

    async def _render(self, lock: ProductionStyleLock) -> SmokeRenderEvidence:
        if self._generator.name.startswith("fake:"):
            # An offline engine cannot prove a real pipeline is executable, and
            # a receipt it produced would unlock production on synthetic bytes.
            raise StyleLockError(
                "STYLE_LOCK_UNAPPROVED",
                f"Smoke evidence requires a real render engine, not "
                f"'{self._generator.name}'.",
            )
        request = KeyframeGenerationRequest(
            shot_contract_id="style-lock-smoke",
            camera_constraints={"angle": "straight-on neutral reference framing"},
            action_constraints={"primary_action": "static reference pose"},
            visual_constraints={
                "latent_mode": "empty",
                "prompt": SMOKE_PROMPT,
                "sampling_steps": lock.steps,
                "guidance_scale": lock.cfg,
                "sampler_name": lock.sampler,
                "denoise": lock.denoise,
            },
            width=lock.width,
            height=lock.height,
            seed=self._seed,
        )
        started = time.monotonic()
        generated: GeneratedKeyframe = await self._generator.generate_keyframe(request)
        duration = time.monotonic() - started
        if not generated.image_bytes:
            raise StyleLockError(
                "STYLE_LOCK_UNAPPROVED", "Smoke render returned no image bytes."
            )
        if (generated.width, generated.height) != (lock.width, lock.height):
            raise StyleLockError(
                "STYLE_LOCK_UNAPPROVED",
                f"Smoke render returned {generated.width}x{generated.height}, "
                f"not the locked {lock.width}x{lock.height}.",
            )
        return SmokeRenderEvidence(
            image_bytes=generated.image_bytes,
            width=generated.width,
            height=generated.height,
            provider=str(generated.metadata.get("provider", self._generator.name)),
            duration_sec=duration,
            content_hash=hashlib.sha256(generated.image_bytes).hexdigest(),
            provider_asset_id=generated.provider_asset_id,
        )

    def _receipt(
        self,
        project: SeriesProject,
        lock: ProductionStyleLock,
        verification: dict[str, Any],
        evidence: SmokeRenderEvidence,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "receipt_type": "PRODUCTION_STYLE_LOCK_SMOKE",
            "status": "PASSED",
            "passed": True,
            "series_id": project.series_id,
            "style_id": lock.style_id,
            "style_version": lock.style_version,
            "lock_version": lock.lock_version,
            # The field mark_production_compatible binds on.
            "production_lock_digest": lock.digest,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "seed": self._seed,
            "verification": verification,
            "render": evidence.to_dict(),
            "render_settings": {
                "width": lock.width,
                "height": lock.height,
                "sampler": lock.sampler,
                "steps": lock.steps,
                "cfg": lock.cfg,
                "denoise": lock.denoise,
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_project(self, project_path: str | Path) -> SeriesProject:
        source = self._resolve(project_path)
        try:
            return SeriesProject.from_dict(
                json.loads(self._read(source, "series project").decode("utf-8"))
            )
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise StyleLockError(
                "STYLE_LOCK_MISSING",
                f"Active series manifest is unavailable or invalid: {source}",
            ) from error

    def _load_lock(self, project: SeriesProject) -> ProductionStyleLock:
        source = self._resolve(project.production_style_lock)
        try:
            payload = json.loads(self._read(source, "production lock").decode("utf-8"))
            return ProductionStyleLock.from_dict(payload)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise StyleLockError(
                "STYLE_LOCK_MISSING",
                f"Production style lock is unavailable or invalid: {source}",
            ) from error

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        resolved = (
            candidate if candidate.is_absolute() else self._workspace_root / candidate
        ).resolve()
        try:
            resolved.relative_to(self._workspace_root)
        except ValueError as error:
            raise StyleLockError(
                "STYLE_LOCK_TAMPERED", "Smoke evidence paths must stay in the workspace."
            ) from error
        return resolved

    @staticmethod
    def _read(path: Path, label: str) -> bytes:
        try:
            return path.read_bytes()
        except OSError as error:
            raise StyleLockError(
                "STYLE_LOCK_MISSING", f"Required {label} is unreadable: {path}"
            ) from error

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


__all__ = ["DEFAULT_SEED", "SMOKE_PROMPT", "SmokeRenderEvidence", "StyleLockSmokeService"]
