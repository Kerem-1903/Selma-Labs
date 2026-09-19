from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.application.services.character_qc_calibration_service import (
    CharacterQcCalibrationService,
)


def _write_image(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_create_manifest_preserves_automatic_qc_and_leaves_human_labels_empty(tmp_path):
    root = tmp_path / "storage"
    candidate = root / "benchmarks" / "benchmark" / "animagine" / "akira" / "candidates" / "one.png"
    quarantine = root / "benchmarks" / "benchmark" / "illustrious" / "kaito" / "quarantine" / "two.png"
    _write_image(candidate, b"candidate")
    _write_image(quarantine, b"quarantine")
    (candidate.parents[1] / "run-manifest.json").write_text(
        json.dumps(
            {
                "attempts": [
                    {
                        "storage_key": "benchmarks/benchmark/animagine/akira/candidates/one.png",
                        "state": "QC_PASSED",
                        "qc_report": {"reasons": [], "checks": {"exactly_one_person": True}},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    manifest = CharacterQcCalibrationService().create_manifest(
        storage_root=root,
        benchmark_prefix="benchmarks/benchmark",
        minimum_images=1,
    )

    assert manifest["sample_count"] == 2
    assert manifest["sample_sufficient"] is True
    assert {item["source_kind"] for item in manifest["items"]} == {
        "candidate",
        "quarantine",
    }
    assert all(item["human_review"]["decision"] is None for item in manifest["items"])
    passed = next(item for item in manifest["items"] if item["source_kind"] == "candidate")
    assert passed["automatic_qc"]["passed"] is True
    assert passed["automatic_qc"]["checks"]["exactly_one_person"] is True


def test_summary_remains_pending_until_complete_human_review(tmp_path):
    service = CharacterQcCalibrationService()
    manifest = {
        "items": [
            {
                "automatic_qc": {"passed": True},
                "human_review": {
                    "decision": "ACCEPT",
                    "scores": {
                        "identity_similarity": 5,
                        "anatomy": 4,
                        "style": 4,
                        "costume": 5,
                        "artifacts": 5,
                    },
                    "reviewer": "operator",
                    "reviewed_at": "2026-09-11T00:00:00Z",
                },
            },
            {
                "automatic_qc": {"passed": False},
                "human_review": {
                    "decision": None,
                    "scores": {},
                    "reviewer": "",
                    "reviewed_at": "",
                },
            },
        ]
    }

    summary = service.summarize(manifest)

    assert summary["status"] == "PENDING_HUMAN_REVIEW"
    assert summary["reviewed_count"] == 1
    assert summary["pending_count"] == 1
    assert summary["false_accepts"] is None


def test_summary_reports_false_accepts_and_rejects_after_complete_review():
    service = CharacterQcCalibrationService()

    def reviewed(passed: bool, decision: str) -> dict:
        return {
            "automatic_qc": {"passed": passed},
            "human_review": {
                "decision": decision,
                "scores": {field: 3 for field in (
                    "identity_similarity", "anatomy", "style", "costume", "artifacts"
                )},
                "reviewer": "operator",
                "reviewed_at": "2026-09-11T00:00:00Z",
            },
        }

    summary = service.summarize(
        {"items": [reviewed(True, "REJECT"), reviewed(False, "ACCEPT")]}
    )

    assert summary["status"] == "COMPLETE"
    assert summary["false_accepts"] == 1
    assert summary["false_rejects"] == 1
    assert summary["false_accept_rate"] == 0.5
    assert summary["false_reject_rate"] == 0.5
    assert summary["average_scores"]["anatomy"] == 3.0


def test_manifest_rejects_escaping_prefix(tmp_path):
    with pytest.raises(ValueError, match="inside storage root"):
        CharacterQcCalibrationService().create_manifest(
            storage_root=tmp_path,
            benchmark_prefix="../outside",
        )
