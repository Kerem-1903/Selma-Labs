from __future__ import annotations

import json
import os
import socket
import time

import pytest

from core.application.services.comfy_watchdog_service import ComfyJobWatchdog
from core.application.services.model_lock_service import load_model_lock
from core.application.services.production_manifest_service import (
    ProductionManifestService,
    ProductionWorkLockedError,
)
from core.application.services.production_preflight_service import (
    PreflightOptions,
    ProductionPreflightService,
)
from core.application.services.thermal_guard_service import ThermalGuardService
from core.domain.value_objects.production_infra import (
    ModelLock,
    ModelLockEntry,
    ThermalPolicy,
    WatchdogPolicy,
)


class Response:
    status = 200

    def __init__(self, payload) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        del exc_type, exc, traceback

    def read(self):
        return json.dumps(self.payload).encode()


def test_repository_model_lock_records_real_hashes_for_required_models():
    lock = load_model_lock("models.lock.json")

    assert lock.entry("ip_adapter").sha256 == (
        "3f5062b8400c94b7159665b21ba5c62acdcd7682262743d7f2aefedef00e6581"
    )
    assert lock.entry("clip_vision").sha256 != "NOT_INSTALLED"
    assert lock.entry("controlnet_openpose").sha256 != "NOT_INSTALLED"
    assert lock.entry("checkpoint").sha256 == (
        "c2a1a3eaa13d4c107dc7e00c3fe830cab427aa026362740ea094745b3422a331"
    )
    assert lock.entry("face_detector").sha256 == (
        "717923c19b3f4bbf5250b728f1fa6b2cb72a33aed1d236ea9caf0e21ad943e5f"
    )
    assert lock.entry("pose_detector").sha256 == (
        "c6fa93dd1ee4a2c18c900a45c1d864a1c6f7aba75d84f91648a30b7fb641d212"
    )


def test_preflight_fails_closed_and_skips_dry_run_when_model_is_missing(tmp_path):
    missing = ModelLockEntry(
        role="checkpoint",
        filename="missing.safetensors",
        relative_path="models/missing.safetensors",
        sha256="b" * 64,
        size_bytes=1,
    )
    lock = ModelLock(1, str(tmp_path), (missing,))

    def opener(request, timeout):
        del timeout
        url = request if isinstance(request, str) else request.full_url
        if url.endswith("/system_stats"):
            return Response({"system": {}})
        if url.endswith("/object_info"):
            from core.application.services.production_preflight_service import (
                REQUIRED_NODE_CLASSES,
            )

            return Response({name: {} for name in REQUIRED_NODE_CLASSES})
        if url.endswith("/queue"):
            return Response({"queue_running": [], "queue_pending": []})
        raise AssertionError(url)

    report = ProductionPreflightService(
        PreflightOptions(
            comfyui_api_url="http://127.0.0.1:8188",
            output_dir=tmp_path / "output",
            min_free_disk_gb=0,
            min_free_ram_gb=0,
            run_test_job=True,
        ),
        opener=opener,
        free_ram_bytes=lambda: 1024,
    ).run(lock)

    assert not report.ok
    assert any(check.name.startswith("model:checkpoint") for check in report.failures)
    dry_run = next(check for check in report.checks if check.name == "test_workflow")
    assert not dry_run.passed
    assert "prerequisites failed" in dry_run.detail


async def test_async_watchdog_interrupts_stuck_job_and_retries():
    watchdog = ComfyJobWatchdog(
        WatchdogPolicy(
            no_progress_timeout_sec=0.01,
            absolute_job_timeout_sec=0.2,
            retry_limit=1,
        )
    )
    attempts: list[int] = []
    interrupted: list[str] = []

    async def submit(attempt: int) -> str:
        attempts.append(attempt)
        return f"prompt-{attempt}"

    async def poll(prompt_id: str) -> str:
        del prompt_id
        return "unchanged"

    async def finished(prompt_id: str):
        return "done" if prompt_id == "prompt-1" else None

    async def interrupt(prompt_id: str) -> None:
        interrupted.append(prompt_id)

    result, outcome = await watchdog.run_async(
        submit=submit,
        poll=poll,
        finished=finished,
        interrupt=interrupt,
    )

    assert result == "done"
    assert attempts == [0, 1]
    assert interrupted == ["prompt-0"]
    assert outcome.attempts == 2


def test_thermal_guard_applies_minimum_delay_when_temperature_is_unsupported():
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    guard = ThermalGuardService(
        ThermalPolicy(minimum_inter_job_delay_sec=10),
        probe=lambda: None,
        clock=lambda: now[0],
        sleep=sleep,
    )
    after = guard.after_job()
    before = guard.before_job()

    assert after.waited_sec == 10
    assert before.waited_sec == 0
    assert sleeps == [10]


def test_thermal_guard_waits_until_gpu_reaches_safe_temperature():
    now = [0.0]
    temperatures = iter((81.0, 77.0, 74.0))

    def sleep(seconds: float) -> None:
        now[0] += seconds

    guard = ThermalGuardService(
        ThermalPolicy(
            minimum_inter_job_delay_sec=0,
            thermal_threshold_celsius=75,
            thermal_poll_interval_sec=5,
            thermal_max_wait_sec=300,
        ),
        probe=lambda: next(temperatures),
        clock=lambda: now[0],
        sleep=sleep,
    )

    decision = guard.after_job()

    assert not decision.paused
    assert decision.waited_sec == 10
    assert decision.temperature_celsius == 74


def test_thermal_guard_pauses_after_maximum_hot_wait():
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    guard = ThermalGuardService(
        ThermalPolicy(
            minimum_inter_job_delay_sec=0,
            thermal_threshold_celsius=75,
            thermal_poll_interval_sec=5,
            thermal_max_wait_sec=10,
        ),
        probe=lambda: 90.0,
        clock=lambda: now[0],
        sleep=sleep,
    )

    decision = guard.after_job()

    assert decision.paused
    assert decision.waited_sec == 10


def test_manifest_is_atomic_and_work_lock_is_exclusive(tmp_path):
    service = ProductionManifestService(tmp_path)
    root = "characters/kaito/v1"

    with service.work_lock(root):
        with pytest.raises(ProductionWorkLockedError), service.work_lock(root):
            pass
        service.initialize(relative_root=root)
        service.record_asset(
            relative_root=root,
            asset_id="FRONT:attempt-1",
            storage_key=f"{root}/views/front.png",
            content_hash="c" * 64,
            seed=12,
            model_hashes={"checkpoint": "d" * 64},
            reference_hashes=("e" * 64,),
            qc_metrics={"passed": True},
            render_duration_sec=1.25,
            peak_vram_mb=4096,
            state="QC_PASSED",
        )
        service.finalize(relative_root=root, status="PENDING_HUMAN_REVIEW")

    target = tmp_path / root / "manifest.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["status"] == "PENDING_HUMAN_REVIEW"
    assert payload["assets"][0]["peak_vram_mb"] == 4096
    assert not (tmp_path / root / ".lock").exists()
    assert list((tmp_path / root).glob("*.tmp")) == []


def test_manifest_reclaims_expired_lock_owned_by_dead_process(tmp_path):
    service = ProductionManifestService(tmp_path, stale_lock_timeout_sec=1)
    root = "characters/kaito/v1"
    lock_path = tmp_path / root / ".lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps(
            {
                "token": "abandoned",
                "pid": 999_999_999,
                "hostname": socket.gethostname(),
                "created_at": time.time() - 60,
            }
        ),
        encoding="utf-8",
    )

    with service.work_lock(root):
        current = json.loads(lock_path.read_text(encoding="utf-8"))
        assert current["pid"] == os.getpid()
        assert current["token"] != "abandoned"

    assert not lock_path.exists()
