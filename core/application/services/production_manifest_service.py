"""Atomic per-character production manifest and exclusive work lock."""

from __future__ import annotations

import json
import os
import socket
import tempfile
import time
import uuid
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from typing_extensions import Self


class ProductionWorkLockedError(RuntimeError):
    pass


class _WorkLock(AbstractContextManager["_WorkLock"]):
    def __init__(self, path: Path, stale_after_sec: float) -> None:
        self._path = path
        self._token = uuid.uuid4().hex
        self._stale_after_sec = stale_after_sec

    @staticmethod
    def _process_is_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def _reclaim_if_stale(self) -> bool:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            created_at = float(payload.get("created_at", 0))
            pid = int(payload.get("pid", 0))
            owner_host = str(payload.get("hostname", ""))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            try:
                created_at = self._path.stat().st_mtime
            except OSError:
                return True
            pid = 0
            owner_host = ""
        age = max(0.0, time.time() - created_at)
        local_owner = not owner_host or owner_host == socket.gethostname()
        stale = age >= self._stale_after_sec and (
            not local_owner or not self._process_is_alive(pid)
        )
        if not stale:
            return False
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
        return True

    def __enter__(self) -> Self:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                descriptor = os.open(
                    self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
                break
            except FileExistsError as error:
                if attempt == 0 and self._reclaim_if_stale():
                    continue
                raise ProductionWorkLockedError(
                    f"Production work lock already exists: {self._path}"
                ) from error
        payload = json.dumps(
            {
                "token": self._token,
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "created_at": time.time(),
            }
        ).encode("utf-8")
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        try:
            current = json.loads(self._path.read_text(encoding="utf-8"))
            if current.get("token") == self._token:
                self._path.unlink()
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass


class ProductionManifestService:
    def __init__(
        self, storage_root: str | Path, *, stale_lock_timeout_sec: float = 21600
    ) -> None:
        if stale_lock_timeout_sec <= 0:
            raise ValueError("stale_lock_timeout_sec must be positive")
        self._storage_root = Path(storage_root).resolve()
        self._stale_lock_timeout_sec = stale_lock_timeout_sec

    def work_lock(self, relative_root: str) -> AbstractContextManager[Any]:
        return _WorkLock(
            self._resolve(relative_root) / ".lock",
            self._stale_lock_timeout_sec,
        )

    def initialize(self, *, relative_root: str) -> Path:
        target = self._resolve(relative_root) / "manifest.json"
        if target.is_file():
            return target
        self._atomic_write(
            target,
            {"schema_version": 1, "status": "IN_PROGRESS", "assets": []},
        )
        return target

    def record_asset(
        self,
        *,
        relative_root: str,
        asset_id: str,
        storage_key: str,
        content_hash: str,
        seed: int,
        model_hashes: dict[str, str],
        reference_hashes: tuple[str, ...],
        qc_metrics: dict[str, Any],
        render_duration_sec: float,
        peak_vram_mb: float | None,
        state: str,
        prompt_hash: str = "",
        workflow_hash: str = "",
        run_id: str = "",
    ) -> Path:
        root = self._resolve(relative_root)
        target = root / "manifest.json"
        root.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "schema_version": 1,
            "status": "IN_PROGRESS",
            "assets": [],
        }
        if target.is_file():
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict) or not isinstance(
                loaded.get("assets"), list
            ):
                raise ValueError(f"Production manifest is malformed: {target}")
            payload = loaded
        entry = {
            "asset_id": asset_id,
            "storage_key": storage_key,
            "content_hash": content_hash,
            "seed": seed,
            "model_hashes": dict(model_hashes),
            "reference_hashes": list(reference_hashes),
            "qc_metrics": dict(qc_metrics),
            "render_duration_sec": round(max(0.0, render_duration_sec), 3),
            "peak_vram_mb": peak_vram_mb,
            "state": state,
            "prompt_hash": prompt_hash,
            "workflow_hash": workflow_hash,
            "run_id": run_id,
        }
        assets = [item for item in payload["assets"] if item.get("asset_id") != asset_id]
        assets.append(entry)
        payload["assets"] = assets
        payload["status"] = "BLOCKED" if state == "BLOCKED" else "IN_PROGRESS"
        self._atomic_write(target, payload)
        return target

    def finalize(self, *, relative_root: str, status: str) -> Path:
        target = self._resolve(relative_root) / "manifest.json"
        if not target.is_file():
            raise FileNotFoundError(f"Production manifest was not created: {target}")
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["status"] = status
        self._atomic_write(target, payload)
        return target

    def _resolve(self, relative_root: str) -> Path:
        candidate = (self._storage_root / relative_root).resolve()
        try:
            candidate.relative_to(self._storage_root)
        except ValueError as error:
            raise ValueError("Production path escapes the storage root.") from error
        return candidate

    @staticmethod
    def _atomic_write(target: Path, payload: dict[str, Any]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        finally:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)
