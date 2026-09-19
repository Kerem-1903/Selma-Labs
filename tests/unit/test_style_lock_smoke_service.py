"""Tests for the production style-lock smoke receipt producer.

The chain this covers used to be uncompletable: ``mark_production_compatible``
demanded a receipt bound to the pending lock digest, and nothing in the
repository produced one. These tests prove the receipt is derived from a real
run, that it completes the lock, and that every tampering path stays closed.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from cli.main import build_parser
from core.application.services.series_style_lock_service import SeriesStyleLockService
from core.application.services.style_lock_smoke_service import StyleLockSmokeService
from core.domain.exceptions import StyleLockError
from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import (
    KeyframeGenerationRequest,
)
from core.domain.value_objects.style_lock import (
    LOCK_COMPATIBLE,
    LOCK_PENDING_SMOKE,
    ProductionStyleLock,
)

ROOT = Path(__file__).parents[2]
PROJECT = ROOT / "config/series/selma-anime-v1.json"
STYLE_REFERENCE = ROOT / "assets/series/selma-anime-v1/style/approved-style-reference.png"
WORKFLOW = ROOT / "assets/comfyui_keyframe_workflow.json"

WEIGHT_BYTES = b"locked-weight-bytes"
LOCKED_WIDTH = 768
LOCKED_HEIGHT = 1152


def _png(width: int = LOCKED_WIDTH, height: int = LOCKED_HEIGHT) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (240, 240, 240)).save(buffer, format="PNG")
    return buffer.getvalue()


class _StubGenerator(KeyframeGenerationPort):
    """Stands in for a real engine without pretending to be an offline one."""

    def __init__(
        self,
        *,
        name: str = "comfyui:style-smoke-stub",
        width: int = LOCKED_WIDTH,
        height: int = LOCKED_HEIGHT,
        image_bytes: bytes | None = None,
    ) -> None:
        self._name = name
        self._width = width
        self._height = height
        self._image_bytes = image_bytes
        self.requests: list[KeyframeGenerationRequest] = []

    @property
    def name(self) -> str:
        return self._name

    async def generate_keyframe(
        self, request: KeyframeGenerationRequest
    ) -> GeneratedKeyframe:
        self.requests.append(request)
        return GeneratedKeyframe(
            image_bytes=self._image_bytes or _png(),
            content_type="image/png",
            width=self._width,
            height=self._height,
            provider_asset_id="stub-asset",
            metadata={"provider": "stub-engine"},
        )


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Build a self-contained workspace holding a *pending* production lock."""
    comfy = tmp_path / "comfyui"
    weight = comfy / "models" / "checkpoints" / "base.safetensors"
    weight.parent.mkdir(parents=True, exist_ok=True)
    weight.write_bytes(WEIGHT_BYTES)
    model_lock = {
        "schema_version": 1,
        "comfyui_root": str(comfy),
        "models": [
            {
                "role": "checkpoint",
                "filename": "base.safetensors",
                "relative_path": "models/checkpoints/base.safetensors",
                "sha256": hashlib.sha256(WEIGHT_BYTES).hexdigest(),
                "size_bytes": len(WEIGHT_BYTES),
                "required": True,
            }
        ],
    }
    (tmp_path / "models.lock.json").write_text(json.dumps(model_lock), encoding="utf-8")
    shutil.copyfile(STYLE_REFERENCE, tmp_path / "style.png")
    shutil.copyfile(WORKFLOW, tmp_path / "workflow.json")
    (tmp_path / "cast.json").write_text(
        json.dumps({"schema_version": 1, "series_id": "selma-anime-v1", "members": []}),
        encoding="utf-8",
    )

    project = json.loads(PROJECT.read_text(encoding="utf-8"))
    project["style_bible"]["reference_asset"] = "style.png"
    project["character_registry"] = "cast.json"
    project["model_lock"] = "models.lock.json"
    project["style_approval_receipt"] = "style-approval.json"
    project["production_style_lock"] = "production-style-lock.json"
    project_path = tmp_path / "series.json"
    project_path.write_text(json.dumps(project), encoding="utf-8")

    service = SeriesStyleLockService(tmp_path)
    service.write_style_approval(
        project_path,
        approved_by="operator",
        approval_criteria=("style language reviewed",),
    )
    service.promote_style(project_path)
    service.write_production_lock(
        project_path,
        workflow_path=tmp_path / "workflow.json",
        style_approval_receipt_sha256=hashlib.sha256(
            (tmp_path / "style-approval.json").read_bytes()
        ).hexdigest(),
        width=LOCKED_WIDTH,
        height=LOCKED_HEIGHT,
        sampler="euler",
        steps=24,
        cfg=5.0,
        denoise=0.65,
    )
    return tmp_path, project_path


def _service(workspace: Path, **overrides) -> StyleLockSmokeService:
    kwargs = {"generator": _StubGenerator(), **overrides}
    return StyleLockSmokeService(workspace, **kwargs)


def _run(
    service: StyleLockSmokeService,
    workspace: Path,
    project_path: Path | str,
    *,
    receipt_name: str = "receipt.json",
    image_name: str | None = None,
    workflow_path: Path | None = None,
) -> dict:
    return asyncio.run(
        service.run(
            project_path,
            workflow_path=workflow_path or workspace / "workflow.json",
            receipt_path=workspace / receipt_name,
            image_path=None if image_name is None else workspace / image_name,
        )
    )


def _pending_digest(workspace: Path) -> str:
    payload = json.loads((workspace / "production-style-lock.json").read_text("utf-8"))
    assert payload["compatibility_status"] == LOCK_PENDING_SMOKE
    return ProductionStyleLock.from_dict(payload).digest


def test_smoke_receipt_binds_the_pending_lock_and_completes_it(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    service = _service(workspace)
    receipt_path = workspace / "smoke-receipt.json"

    receipt = _run(
        service, workspace, project_path, receipt_name="smoke-receipt.json"
    )

    assert receipt["status"] == "PASSED"
    assert receipt["passed"] is True
    assert receipt["production_lock_digest"] == _pending_digest(workspace)
    assert receipt_path.is_file()

    # The whole point: the produced receipt is the one the lock demands.
    completed = SeriesStyleLockService(workspace).mark_production_compatible(
        project_path, smoke_test_receipt_path=receipt_path
    )

    assert completed.compatibility_status == LOCK_COMPATIBLE
    assert completed.production_eligible is True
    assert completed.smoke_test_receipt_sha256 == hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()


def test_smoke_receipt_records_measured_evidence_only(tmp_path):
    workspace, project_path = _workspace(tmp_path)

    receipt = _run(_service(workspace), workspace, project_path)

    assert receipt["verification"]["workflow_id"] == "workflow.json"
    assert receipt["verification"]["model_verification"] == "size"
    assert receipt["verification"]["roles"]["checkpoint"].startswith("size-match")
    assert receipt["render"]["provider"] == "stub-engine"
    assert receipt["render"]["content_hash"] == hashlib.sha256(_png()).hexdigest()
    assert receipt["render_settings"] == {
        "width": LOCKED_WIDTH,
        "height": LOCKED_HEIGHT,
        "sampler": "euler",
        "steps": 24,
        "cfg": 5.0,
        "denoise": 0.65,
    }


def test_smoke_renders_through_the_locked_sampler_settings(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    generator = _StubGenerator()

    _run(_service(workspace, generator=generator), workspace, project_path)

    request = generator.requests[0]
    assert (request.width, request.height) == (LOCKED_WIDTH, LOCKED_HEIGHT)
    assert request.visual_constraints["sampling_steps"] == 24
    assert request.visual_constraints["guidance_scale"] == 5.0
    assert request.visual_constraints["sampler_name"] == "euler"
    # A smoke that needed a character reference would not be a smoke.
    assert request.visual_constraints["latent_mode"] == "empty"
    assert not request.reference_storage_keys


def test_smoke_is_refused_for_an_offline_engine(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    service = _service(workspace, generator=_StubGenerator(name="fake:keyframe"))

    with pytest.raises(StyleLockError) as refused:
        _run(service, workspace, project_path)

    # A fake engine would unlock production on synthetic bytes.
    assert refused.value.reason == "STYLE_LOCK_UNAPPROVED"
    assert "real render engine" in refused.value.detail


def test_smoke_refuses_when_the_locked_workflow_changed(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    (workspace / "workflow.json").write_bytes(b"{}")

    with pytest.raises(StyleLockError) as refused:
        _run(_service(workspace), workspace, project_path)

    assert refused.value.reason == "STYLE_LOCK_TAMPERED"
    assert "Workflow bytes" in refused.value.detail


def test_smoke_refuses_a_different_workflow_file(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    shutil.copyfile(workspace / "workflow.json", workspace / "other-workflow.json")

    with pytest.raises(StyleLockError) as refused:
        _run(
            _service(workspace),
            workspace,
            project_path,
            workflow_path=workspace / "other-workflow.json",
        )

    assert "not the locked workflow" in refused.value.detail


def test_smoke_refuses_a_missing_locked_weight(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    (workspace / "comfyui/models/checkpoints/base.safetensors").unlink()

    with pytest.raises(StyleLockError) as refused:
        _run(_service(workspace), workspace, project_path)

    assert refused.value.reason == "STYLE_LOCK_MISSING"
    assert "checkpoint" in refused.value.detail


def test_smoke_refuses_a_resized_locked_weight(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    (workspace / "comfyui/models/checkpoints/base.safetensors").write_bytes(b"short")

    with pytest.raises(StyleLockError) as refused:
        _run(_service(workspace), workspace, project_path)

    assert refused.value.reason == "STYLE_LOCK_TAMPERED"
    assert "changed size" in refused.value.detail


def test_full_model_hash_catches_a_same_size_weight_swap(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    (workspace / "comfyui/models/checkpoints/base.safetensors").write_bytes(
        b"X" * len(WEIGHT_BYTES)
    )

    # Size-only verification cannot see this; the explicit full hash must.
    receipt = _run(_service(workspace), workspace, project_path)
    assert receipt["status"] == "PASSED"

    with pytest.raises(StyleLockError) as refused:
        _run(_service(workspace, full_model_hash=True), workspace, project_path)

    assert refused.value.reason == "STYLE_LOCK_TAMPERED"
    assert "changed bytes" in refused.value.detail


def test_smoke_refuses_a_changed_model_lock(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    payload = json.loads((workspace / "models.lock.json").read_text("utf-8"))
    payload["models"][0]["note"] = "edited after the lock was written"
    (workspace / "models.lock.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StyleLockError) as refused:
        _run(_service(workspace), workspace, project_path)

    assert "Model lock bytes" in refused.value.detail


def test_smoke_refuses_a_render_at_the_wrong_size(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    service = _service(workspace, generator=_StubGenerator(width=512, height=512))

    with pytest.raises(StyleLockError) as refused:
        _run(service, workspace, project_path)

    assert refused.value.reason == "STYLE_LOCK_UNAPPROVED"
    assert "not the locked" in refused.value.detail


def test_smoke_refuses_to_re_attest_a_completed_lock(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    _run(
        _service(workspace), workspace, project_path, receipt_name="smoke-receipt.json"
    )
    SeriesStyleLockService(workspace).mark_production_compatible(
        project_path, smoke_test_receipt_path=workspace / "smoke-receipt.json"
    )

    with pytest.raises(StyleLockError) as refused:
        _run(_service(workspace), workspace, project_path)

    assert refused.value.reason == "STYLE_LOCK_TAMPERED"
    assert "already compatible" in refused.value.detail


def test_smoke_refuses_a_missing_pending_lock(tmp_path):
    workspace, project_path = _workspace(tmp_path)
    (workspace / "production-style-lock.json").unlink()

    with pytest.raises(StyleLockError) as refused:
        _run(_service(workspace), workspace, project_path)

    assert refused.value.reason == "STYLE_LOCK_MISSING"


def test_smoke_writes_the_frame_beside_the_receipt(tmp_path):
    workspace, project_path = _workspace(tmp_path)

    _run(
        _service(workspace),
        workspace,
        project_path,
        receipt_name="smoke-receipt.json",
        image_name="smoke-receipt.png",
    )

    assert (workspace / "smoke-receipt.png").read_bytes() == _png()


def test_smoke_paths_may_not_leave_the_workspace(tmp_path):
    workspace, _project_path = _workspace(tmp_path)

    with pytest.raises(StyleLockError) as refused:
        _run(_service(workspace), workspace, Path("../outside.json"))

    assert refused.value.reason == "STYLE_LOCK_TAMPERED"


def test_cli_exposes_the_smoke_production_lock_command(tmp_path):
    arguments = build_parser().parse_args(
        [
            "series",
            "smoke-production-lock",
            "--receipt",
            str(tmp_path / "receipt.json"),
        ]
    )

    assert arguments.series_command == "smoke-production-lock"
    assert arguments.project == "config/series/selma-anime-v1.json"
    assert arguments.workflow == "assets/comfyui_keyframe_workflow.json"
    assert arguments.full_model_hash is False
    assert arguments.seed is None
