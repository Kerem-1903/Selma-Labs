"""Prepare reproducible Wan2.2 I2V inputs without invoking a GPU provider."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.domain.value_objects.trailer_plan import TrailerPlan
from core.domain.value_objects.wan22_animation_package import Wan22AnimationPackage
from core.domain.value_objects.wan22_render_profile import Wan22RenderProfile


class Wan22PackageService:
    """Translate approved-source metadata into auditable Wan shot packages."""

    def build(
        self,
        plan: TrailerPlan,
        sources: Mapping[str, Mapping[str, Any]],
        *,
        workflow_hash: str = "PENDING",
        model_revision: str = "UNPINNED_PENDING_RENTED_GPU_TEST",
        width: int = 832,
        height: int = 480,
        seed_base: int = 1903,
        render_profile: Wan22RenderProfile | None = None,
    ) -> tuple[Wan22AnimationPackage, ...]:
        packages: list[Wan22AnimationPackage] = []
        for index, shot in enumerate(plan.shots):
            source = sources.get(shot.shot_id)
            if not isinstance(source, Mapping):
                raise ValueError(  # noqa: TRY004 - a missing mapping is a value/domain error
                    f"Missing Wan source metadata for shot '{shot.shot_id}'."
                )
            frame_count = render_profile.frame_count if render_profile else shot.duration_frames
            fps = render_profile.fps if render_profile else plan.timeline.fps
            packages.append(
                Wan22AnimationPackage(
                    shot_id=shot.shot_id,
                    source_image_key=str(source.get("source_image_key", "")),
                    source_image_hash=str(source.get("source_image_hash", "")),
                    motion_prompt=str(source.get("motion_prompt") or shot.purpose),
                    negative_prompt=str(
                        source.get(
                            "negative_prompt",
                            "identity drift, extra limbs, camera warping, flicker",
                        )
                    ),
                    seed=int(source.get("seed", seed_base + index)),
                    frame_count=frame_count,
                    fps=fps,
                    width=int(source.get("width", width)),
                    height=int(source.get("height", height)),
                    workflow_hash=workflow_hash,
                    model_revision=model_revision,
                    generation_attempt=int(source.get("generation_attempt", 1)),
                    output_video_key=str(source.get("output_video_key", f"wan22/{shot.shot_id}.mp4")),
                )
            )
        return tuple(packages)

    @staticmethod
    def preflight(path: str | Path) -> dict[str, Any]:
        config_path = Path(path)
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("Wan worker configuration must contain an object.")
        required = (
            "provider",
            "container_image",
            "model_revision",
            "persistent_storage",
            "model_files",
            "workflow_path",
            "workflow_hash",
            "provider_auto_stop_enabled",
        )
        missing = [name for name in required if not str(payload.get(name, "")).strip()]
        errors: list[str] = []
        base = config_path.parent

        model_files = payload.get("model_files")
        required_models = {"high_noise", "low_noise", "vae", "umt5"}
        if isinstance(model_files, Mapping):
            absent_models = sorted(required_models - set(model_files))
            errors.extend(f"missing model: {name}" for name in absent_models)
            for name, model in model_files.items():
                if not isinstance(model, Mapping):
                    errors.append(f"invalid model manifest entry: {name}")
                    continue
                Wan22PackageService._check_file_hash(
                    base, model.get("path"), model.get("sha256"), f"model {name}", errors
                )
        elif "model_files" not in missing:
            errors.append("model_files must be a SHA-256 manifest object")

        workflow_path = payload.get("workflow_path")
        workflow_hash = payload.get("workflow_hash")
        if workflow_path and workflow_hash:
            Wan22PackageService._check_file_hash(
                base, workflow_path, workflow_hash, "workflow", errors
            )

        for node in payload.get("custom_nodes", []):
            node_path = Path(str(node))
            node_path = node_path if node_path.is_absolute() else base / node_path
            if not node_path.exists():
                errors.append(f"custom node missing: {node}")

        for binary_name in ("ffmpeg", "ffprobe"):
            binary = str(payload.get(f"{binary_name}_binary", binary_name))
            binary_path = Path(binary)
            if not binary_path.is_file() and shutil.which(binary) is None:
                errors.append(f"{binary_name} is unavailable")

        storage = payload.get("persistent_storage")
        if isinstance(storage, Mapping) and storage.get("type") == "volume":
            volume_path = Path(str(storage.get("path", "")))
            if not volume_path.is_dir():
                errors.append("persistent volume is not mounted")
        elif isinstance(storage, str) and storage and "://" not in storage:
            if not Path(storage).is_dir():
                errors.append("persistent volume is not mounted")

        minimum_vram = int(payload.get("minimum_vram_gb", 0))
        if float(payload.get("vram_gb", 0)) < minimum_vram:
            errors.append("GPU VRAM is below the configured minimum")
        if payload.get("provider_auto_stop_enabled") is not True:
            errors.append("provider auto-stop is not enabled")

        status = (
            "READY"
            if payload.get("status") == "READY" and not missing and not errors
            else "BLOCKED"
        )
        return {
            "status": status,
            "gpu_model": payload.get("gpu_model", ""),
            "vram_gb": payload.get("vram_gb", 0),
            "model_repository": payload.get("model_repository", ""),
            "missing_configuration": missing,
            "preflight_errors": errors,
            "reason": "Worker is configured for a smoke test." if status == "READY" else "Rented-GPU worker is not configured.",
        }

    @staticmethod
    def _check_file_hash(
        base: Path,
        raw_path: Any,
        expected_hash: Any,
        label: str,
        errors: list[str],
    ) -> None:
        candidate = Path(str(raw_path or ""))
        candidate = candidate if candidate.is_absolute() else base / candidate
        if not candidate.is_file():
            errors.append(f"{label} file is missing")
            return
        expected = str(expected_hash or "").lower()
        if len(expected) != 64:
            errors.append(f"{label} SHA-256 is invalid")
            return
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if digest != expected:
            errors.append(f"{label} SHA-256 mismatch")
