"""Model lock service — spec §4 / §4.2.

Model filenames are never hard-coded in production code; they live in
``models.lock.json`` with SHA-256 identity. This service loads, generates and
verifies the lock against the files actually on disk under the ComfyUI root.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from core.domain.value_objects.production_infra import (
    ModelLock,
    ModelLockEntry,
    PreflightCheck,
)

CHUNK_SIZE = 4 * 1024 * 1024


def sha256_file(path: str | Path) -> tuple[str, int]:
    """Streaming SHA-256; returns (hex_digest, size_bytes)."""
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def load_model_lock(path: str | Path) -> ModelLock:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    lock = ModelLock.from_dict(data)
    if not lock.comfyui_root:
        raise ValueError(f"model lock {path} has no comfyui_root")
    if not lock.entries:
        raise ValueError(f"model lock {path} has no model entries")
    return lock


def generate_model_lock(
    comfyui_root: str | Path,
    roles: dict[str, dict[str, Any]],
) -> ModelLock:
    """Hash real files into a lock.

    ``roles`` maps role name -> dict with keys: ``filename``, ``subdir`` and
    optional ``required`` (default True) and ``note``. Missing optional files
    are skipped; missing required files raise FileNotFoundError.
    """
    root = Path(comfyui_root).expanduser()
    entries: list[ModelLockEntry] = []
    for role, spec in roles.items():
        path = root / spec["subdir"] / spec["filename"]
        required = bool(spec.get("required", True))
        if not path.is_file():
            if required:
                raise FileNotFoundError(f"locked model missing on disk: {path}")
            entries.append(
                ModelLockEntry(
                    role=role,
                    filename=spec["filename"],
                    relative_path=Path(spec["subdir"], spec["filename"]).as_posix(),
                    sha256="NOT_INSTALLED",
                    size_bytes=0,
                    required=False,
                    note=spec.get("note", "not installed at lock time"),
                )
            )
            continue
        digest, size = sha256_file(path)
        entries.append(
            ModelLockEntry(
                role=role,
                filename=spec["filename"],
                relative_path=Path(spec["subdir"], spec["filename"]).as_posix(),
                sha256=digest,
                size_bytes=size,
                required=required,
                note=spec.get("note", ""),
            )
        )
    return ModelLock(schema_version=1, comfyui_root=str(root), entries=tuple(entries))


def save_model_lock(lock: ModelLock, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(lock.to_dict(), indent=2, ensure_ascii=False)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(payload + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


def verify_model_lock(
    lock: ModelLock,
    comfyui_root: str | Path | None = None,
    full_hash: bool = True,
) -> list[PreflightCheck]:
    """Verify every lock entry against disk. Optional missing files degrade to
    warnings; required missing/mismatched files fail."""
    root = Path(comfyui_root or lock.comfyui_root).expanduser()
    checks: list[PreflightCheck] = []
    for entry in lock.entries:
        path = root / Path(entry.relative_path)
        started = time.monotonic()
        if not path.is_file():
            checks.append(
                PreflightCheck(
                    name=f"model:{entry.role}:{entry.filename}",
                    passed=not entry.required,
                    warning=not entry.required,
                    detail=(
                        f"missing: {path}"
                        if entry.required
                        else f"optional component not installed: {entry.note or path}"
                    ),
                    duration_sec=time.monotonic() - started,
                )
            )
            continue
        actual_size = path.stat().st_size
        if not full_hash:
            ok = actual_size == entry.size_bytes
            checks.append(
                PreflightCheck(
                    name=f"model:{entry.role}:{entry.filename}",
                    passed=ok,
                    detail=(
                        "size match (fast mode, hash not verified)"
                        if ok
                        else f"size mismatch: lock={entry.size_bytes} disk={actual_size}"
                    ),
                    duration_sec=time.monotonic() - started,
                )
            )
            continue
        digest, size = sha256_file(path)
        ok = digest == entry.sha256 and size == entry.size_bytes
        checks.append(
            PreflightCheck(
                name=f"model:{entry.role}:{entry.filename}",
                passed=ok,
                detail=(
                    "sha256 verified"
                    if ok
                    else (
                        f"sha256 mismatch: lock={entry.sha256[:12]}… "
                        f"disk={digest[:12]}… (size lock={entry.size_bytes} "
                        f"disk={size})"
                    )
                ),
                duration_sec=time.monotonic() - started,
            )
        )
    return checks
