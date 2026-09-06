"""Production preflight check — spec §4.2.

Every required check must pass before production starts. The service is
transport-injected (``opener``) so unit tests run without ComfyUI.
"""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.application.services.model_lock_service import (
    ModelLock,
    verify_model_lock,
)
from core.domain.value_objects.production_infra import PreflightCheck, PreflightReport

# Node classes the character production workflows depend on.
REQUIRED_NODE_CLASSES: tuple[str, ...] = (
    "KSampler",
    "CheckpointLoaderSimple",
    "CLIPTextEncode",
    "EmptyLatentImage",
    "VAEDecode",
    "SaveImage",
    "LoadImage",
    "IPAdapterUnifiedLoader",
    "IPAdapterAdvanced",
    "ControlNetLoader",
    "ControlNetApplyAdvanced",
)


@dataclass(frozen=True)
class PreflightOptions:
    comfyui_api_url: str
    output_dir: Path
    min_free_disk_gb: float = 40.0
    min_free_ram_gb: float = 4.0
    run_test_job: bool = False
    test_job_timeout_sec: float = 120.0
    request_timeout_sec: float = 10.0


class ProductionPreflightService:
    """Run all spec §4.2 checks and return a serializable report."""

    def __init__(
        self,
        options: PreflightOptions,
        opener: Callable[..., Any] | None = None,
        free_ram_bytes: Callable[[], int] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._options = options
        self._opener = opener or urllib.request.urlopen
        self._free_ram_bytes = free_ram_bytes or _default_free_ram_bytes
        self._clock = clock

    # -- HTTP helpers ------------------------------------------------------
    def _get_json(self, path: str) -> tuple[int, Any, float]:
        url = f"{self._options.comfyui_api_url.rstrip('/')}{path}"
        started = self._clock()
        try:
            with self._opener(url, timeout=self._options.request_timeout_sec) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ComfyUnreachableError(f"{url}: {exc}") from exc
        payload: Any = None
        if body:
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = body[:512].decode("utf-8", errors="replace")
        return status, payload, self._clock() - started

    # -- checks -------------------------------------------------------------
    def run(self, model_lock: ModelLock, full_hash: bool = True) -> PreflightReport:
        checks: list[PreflightCheck] = []

        checks.append(self._check_api_reachable())
        api_up = checks[-1].passed
        if api_up:
            checks.append(self._check_node_classes())
            checks.append(self._check_queue_api())
        else:
            checks.append(
                PreflightCheck(
                    name="node_classes", passed=False, detail="skipped: ComfyUI unreachable"
                )
            )
            checks.append(
                PreflightCheck(
                    name="queue_api", passed=False, detail="skipped: ComfyUI unreachable"
                )
            )

        checks.extend(verify_model_lock(model_lock, full_hash=full_hash))
        checks.append(self._check_disk())
        checks.append(self._check_ram())
        checks.append(self._check_output_writable())
        if self._options.run_test_job:
            prerequisites_ok = api_up and all(
                check.passed or check.warning for check in checks
            )
            checks.append(
                self._check_test_workflow(model_lock)
                if prerequisites_ok
                else PreflightCheck(
                    name="test_workflow",
                    passed=False,
                    detail="skipped: preflight prerequisites failed",
                )
            )
        return PreflightReport(checks=tuple(checks))

    def _check_api_reachable(self) -> PreflightCheck:
        started = self._clock()
        ok = False
        detail = ""
        try:
            status, payload, elapsed = self._get_json("/system_stats")
            ok = status == 200 and isinstance(payload, dict) and "system" in payload
            detail = f"status={status}" if ok else "unexpected /system_stats payload"
        except ComfyUnreachableError as exc:
            return PreflightCheck(
                name="comfyui_api",
                passed=False,
                detail=str(exc),
                duration_sec=self._clock() - started,
            )
        return PreflightCheck(
            name="comfyui_api", passed=ok, detail=detail, duration_sec=elapsed
        )

    def _check_node_classes(self) -> PreflightCheck:
        started = self._clock()
        try:
            _status, payload, elapsed = self._get_json("/object_info")
        except ComfyUnreachableError as exc:
            return PreflightCheck(
                name="node_classes",
                passed=False,
                detail=str(exc),
                duration_sec=self._clock() - started,
            )
        available = set(payload.keys()) if isinstance(payload, dict) else set()
        missing = [name for name in REQUIRED_NODE_CLASSES if name not in available]
        return PreflightCheck(
            name="node_classes",
            passed=not missing,
            detail=(
                "all required node classes present"
                if not missing
                else f"missing: {missing}"
            ),
            duration_sec=elapsed,
        )

    def _check_queue_api(self) -> PreflightCheck:
        started = self._clock()
        try:
            status, _payload, elapsed = self._get_json("/queue")
            ok = status == 200
            detail = f"/queue status={status}"
        except ComfyUnreachableError as exc:
            return PreflightCheck(
                name="queue_api",
                passed=False,
                detail=str(exc),
                duration_sec=self._clock() - started,
            )
        return PreflightCheck(
            name="queue_api", passed=ok, detail=detail, duration_sec=elapsed
        )

    def _check_disk(self) -> PreflightCheck:
        started = self._clock()
        output = self._options.output_dir
        output.mkdir(parents=True, exist_ok=True)
        free_bytes = shutil.disk_usage(output).free
        free_gb = free_bytes / 1024**3
        ok = free_gb >= self._options.min_free_disk_gb
        return PreflightCheck(
            name="disk_free",
            passed=ok,
            detail=(
                f"{free_gb:.1f} GB free (required {self._options.min_free_disk_gb:.1f} GB)"
            ),
            duration_sec=self._clock() - started,
        )

    def _check_ram(self) -> PreflightCheck:
        started = self._clock()
        free_bytes = self._free_ram_bytes()
        if free_bytes < 0:
            return PreflightCheck(
                name="ram_free",
                passed=True,
                warning=True,
                detail="free RAM not measurable on this platform",
                duration_sec=self._clock() - started,
            )
        free_gb = free_bytes / 1024**3
        ok = free_gb >= self._options.min_free_ram_gb
        return PreflightCheck(
            name="ram_free",
            passed=ok,
            detail=(
                f"{free_gb:.1f} GB free (required {self._options.min_free_ram_gb:.1f} GB)"
            ),
            duration_sec=self._clock() - started,
        )

    def _check_output_writable(self) -> PreflightCheck:
        started = self._clock()
        output = self._options.output_dir
        try:
            output.mkdir(parents=True, exist_ok=True)
            probe = output / ".preflight-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            ok, detail = True, "write+delete succeeded"
        except OSError as exc:
            ok, detail = False, f"not writable: {exc}"
        return PreflightCheck(
            name="output_writable", passed=ok, detail=detail,
            duration_sec=self._clock() - started,
        )

    def _check_test_workflow(self, model_lock: ModelLock) -> PreflightCheck:
        """Tiny 4-step generation proving the full prompt→image path works."""
        started = self._clock()
        try:
            prompt_id = self._submit_test_job(model_lock.entry("checkpoint").filename)
        except ComfyUnreachableError as exc:
            return PreflightCheck(
                name="test_workflow",
                passed=False,
                detail=f"submit failed: {exc}",
                duration_sec=self._clock() - started,
            )
        deadline = self._clock() + self._options.test_job_timeout_sec
        while self._clock() < deadline:
            try:
                _status, hist, _ = self._get_json(f"/history/{prompt_id}")
            except ComfyUnreachableError as exc:
                return PreflightCheck(
                    name="test_workflow",
                    passed=False,
                    detail=f"history poll failed: {exc}",
                    duration_sec=self._clock() - started,
                )
            entry = hist.get(prompt_id) if isinstance(hist, dict) else None
            if entry and entry.get("outputs"):
                outputs_ok = any(
                    node.get("images") for node in entry["outputs"].values()
                )
                return PreflightCheck(
                    name="test_workflow",
                    passed=outputs_ok,
                    detail=(
                        "tiny generation completed with an image"
                        if outputs_ok
                        else "job finished without images"
                    ),
                    duration_sec=self._clock() - started,
                )
            if entry and entry.get("status", {}).get("status_str") == "error":
                return PreflightCheck(
                    name="test_workflow",
                    passed=False,
                    detail="ComfyUI reported job error",
                    duration_sec=self._clock() - started,
                )
            time.sleep(0.5)
        return PreflightCheck(
            name="test_workflow",
            passed=False,
            detail=f"no output within {self._options.test_job_timeout_sec:g}s",
            duration_sec=self._clock() - started,
        )

    def _submit_test_job(self, checkpoint_name: str) -> str:
        workflow: dict[str, Any] = {
            "1": {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": checkpoint_name}},
            "2": {"class_type": "EmptyLatentImage",
                  "inputs": {"width": 384, "height": 384, "batch_size": 1}},
            "3": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "anime production art, single character reference",
                              "clip": ["1", 1]}},
            "4": {"class_type": "CLIPTextEncode",
                  "inputs": {"text": "lowres", "clip": ["1", 1]}},
            "5": {"class_type": "KSampler",
                  "inputs": {"seed": 1, "steps": 4, "cfg": 1.0,
                              "sampler_name": "euler", "scheduler": "normal",
                              "denoise": 1.0, "model": ["1", 0],
                              "positive": ["3", 0], "negative": ["4", 0],
                              "latent_image": ["2", 0]}},
            "6": {"class_type": "VAEDecode",
                  "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage",
                  "inputs": {"images": ["6", 0], "filename_prefix": "preflight-probe"}},
        }
        url = f"{self._options.comfyui_api_url.rstrip('/')}/prompt"
        body = json.dumps({"prompt": workflow}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}
        )
        with self._opener(req, timeout=self._options.request_timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload["prompt_id"]


class ComfyUnreachableError(RuntimeError):
    """Raised when the ComfyUI API cannot be reached at all."""


def _default_free_ram_bytes() -> int:
    """Cross-platform free-RAM probe; -1 when unsupported."""
    try:
        import psutil

        return int(psutil.virtual_memory().available)
    except (ImportError, AttributeError, OSError, ValueError):
        pass
    import sys

    if sys.platform == "win32":
        try:
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MemStatus()
            stat.dwLength = ctypes.sizeof(_MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullAvailPhys)
        except (AttributeError, OSError, ValueError):
            return -1
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return -1
