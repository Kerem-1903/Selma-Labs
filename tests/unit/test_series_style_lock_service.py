from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from core.application.services.series_style_lock_service import SeriesStyleLockService
from core.domain.exceptions import StyleLockError
from core.domain.value_objects.style_lock import canonical_style_hash

ROOT = Path(__file__).parents[2]
PROJECT = ROOT / "config/series/selma-anime-v1.json"
STYLE_REFERENCE = ROOT / "assets/series/selma-anime-v1/style/approved-style-reference.png"
WORKFLOW = ROOT / "assets/comfyui_keyframe_workflow.json"


def test_production_resolver_blocks_provisional_series_before_render(tmp_path):
    service = SeriesStyleLockService(ROOT)

    with pytest.raises(StyleLockError) as caught:
        service.resolve_production(
            PROJECT,
            workflow_path=ROOT / "assets/comfyui_keyframe_workflow.json",
        )

    assert caught.value.reason == "STYLE_LOCK_UNAPPROVED"
    assert "PROVISIONAL" in caught.value.detail


def test_canonical_style_hash_excludes_unrelated_series_data():
    style = {
        "style_id": "selma-production-anime-v1",
        "style_version": 1,
        "reference_asset": "style.png",
        "reference_sha256": "a" * 64,
        "width": 1024,
        "height": 1024,
        "rendering_rules": ["clean line art"],
        "composition_rules": ["centered silhouette"],
        "identity_policy": ["never copy identity"],
        "character_registry": "cast-a.json",
        "story_title": "draft one",
    }
    changed = {**style, "character_registry": "cast-b.json", "story_title": "draft two"}

    assert canonical_style_hash(style) == canonical_style_hash(changed)


def _temporary_project(tmp_path: Path) -> Path:
    project = json.loads(PROJECT.read_text(encoding="utf-8"))
    project["style_bible"]["reference_asset"] = "style.png"
    project["character_registry"] = "cast.json"
    project["model_lock"] = "models.lock.json"
    project["style_approval_receipt"] = "style-approval.json"
    project["production_style_lock"] = "production-style-lock.json"
    (tmp_path / "series.json").write_text(
        json.dumps(project), encoding="utf-8"
    )
    shutil.copyfile(STYLE_REFERENCE, tmp_path / "style.png")
    shutil.copyfile(WORKFLOW, tmp_path / "workflow.json")
    shutil.copyfile(ROOT / "models.lock.json", tmp_path / "models.lock.json")
    (tmp_path / "cast.json").write_text(
        json.dumps({"schema_version": 1, "series_id": "selma-anime-v1", "members": []}),
        encoding="utf-8",
    )
    return tmp_path / "series.json"


def test_style_approval_and_pending_production_lock_are_independent(tmp_path):
    project_path = _temporary_project(tmp_path)
    service = SeriesStyleLockService(tmp_path)

    receipt = service.write_style_approval(
        project_path,
        approved_by="operator",
        approval_criteria=("style language reviewed", "identity separation reviewed"),
    )
    assert receipt.artifact_mode == "DISCOVERY"
    assert (tmp_path / "style-approval.json").is_file()

    service.promote_style(project_path)
    promoted = json.loads(project_path.read_text(encoding="utf-8"))
    assert promoted["style_bible"]["status"] == "APPROVED"

    lock = service.write_production_lock(
        project_path,
        workflow_path=tmp_path / "workflow.json",
        style_approval_receipt_sha256=__import__("hashlib").sha256(
            (tmp_path / "style-approval.json").read_bytes()
        ).hexdigest(),
        width=768,
        height=1152,
        sampler="euler",
        steps=24,
        cfg=5.0,
        denoise=0.65,
    )

    assert lock.compatibility_status == "PENDING_SMOKE_TEST"
    assert lock.production_eligible is False
    assert (tmp_path / "production-style-lock.json").is_file()


def test_production_lock_is_immutable_after_creation(tmp_path):
    project_path = _temporary_project(tmp_path)
    service = SeriesStyleLockService(tmp_path)
    service.write_style_approval(
        project_path,
        approved_by="operator",
        approval_criteria=("style reviewed",),
    )
    service.promote_style(project_path)
    import hashlib

    receipt_hash = hashlib.sha256((tmp_path / "style-approval.json").read_bytes()).hexdigest()
    service.write_production_lock(
        project_path,
        workflow_path=tmp_path / "workflow.json",
        style_approval_receipt_sha256=receipt_hash,
        width=768,
        height=1152,
        sampler="euler",
        steps=24,
        cfg=5.0,
        denoise=0.65,
    )

    with pytest.raises(StyleLockError) as caught:
        service.write_production_lock(
            project_path,
            workflow_path=tmp_path / "workflow.json",
            style_approval_receipt_sha256=receipt_hash,
            width=768,
            height=1152,
            sampler="euler",
            steps=30,
            cfg=5.0,
            denoise=0.65,
        )

    assert caught.value.reason == "STYLE_LOCK_TAMPERED"


def test_smoke_compatibility_rejects_non_success_receipt(tmp_path):
    project_path = _temporary_project(tmp_path)
    service = SeriesStyleLockService(tmp_path)
    service.write_style_approval(
        project_path,
        approved_by="operator",
        approval_criteria=("style reviewed",),
    )
    service.promote_style(project_path)
    import hashlib

    service.write_production_lock(
        project_path,
        workflow_path=tmp_path / "workflow.json",
        style_approval_receipt_sha256=hashlib.sha256(
            (tmp_path / "style-approval.json").read_bytes()
        ).hexdigest(),
        width=768,
        height=1152,
        sampler="euler",
        steps=24,
        cfg=5.0,
        denoise=0.65,
    )
    smoke = tmp_path / "smoke.json"
    smoke.write_text(json.dumps({"status": "FAILED", "passed": False}), encoding="utf-8")

    with pytest.raises(StyleLockError) as caught:
        service.mark_production_compatible(
            project_path,
            smoke_test_receipt_path=smoke,
        )

    assert caught.value.reason == "STYLE_LOCK_UNAPPROVED"
