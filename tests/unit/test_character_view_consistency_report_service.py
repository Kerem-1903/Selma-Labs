from __future__ import annotations

import json
from pathlib import Path

from core.application.services.character_view_consistency_report_service import (
    CharacterViewConsistencyReportService,
)

ROOT = Path(__file__).parents[2]


def test_existing_packs_are_reported_as_human_review_required_or_blocked():
    service = CharacterViewConsistencyReportService()
    for character in ("akira", "kaito"):
        root = ROOT / "output" / "production" / "characters" / character / "v5"
        report = service.build(
            pack_path=root / "view-pack.json",
            brief_path=ROOT / "assets" / "character_creation_briefs" / f"{character}.json",
            manifest_path=root / "manifest.json",
        )

        assert report["character_id"] == character
        assert report["summary"]["expected_view_count"] == 7
        assert report["summary"]["present_view_count"] == 7
        assert report["human_required_checks"]
        assert report["status"] in {"HUMAN_REVIEW_REQUIRED", "BLOCKED_AUTOMATIC"}


def test_human_review_rejections_are_attached_per_view(tmp_path):
    root = ROOT / "output" / "production" / "characters" / "akira" / "v5"
    review = ROOT / "output" / "benchmarks" / "akira-v5-human-consistency-review.json"

    report = CharacterViewConsistencyReportService().build(
        pack_path=root / "view-pack.json",
        brief_path=ROOT / "assets" / "character_creation_briefs" / "akira.json",
        manifest_path=root / "manifest.json",
        human_review_path=review,
    )

    assert report["status"] == "REJECTED_HUMAN_REVIEW"
    assert report["human_review"]["decision"] == "REJECT"
    assert report["summary"]["human_rejected_view_count"] == 7
    assert report["views"][0]["human_review"]["decision"] == "REJECT"
    assert report["views"][0]["human_review"]["reasons"]


def test_report_blocks_missing_asset_hash(tmp_path):
    root = tmp_path / "characters" / "akira" / "v5"
    root.mkdir(parents=True)
    source_brief = ROOT / "assets" / "character_creation_briefs" / "akira.json"
    brief = json.loads(source_brief.read_text(encoding="utf-8"))
    pack = {
        "schema_version": 1,
        "character_id": "akira",
        "character_version": 5,
        "brief_hash": "placeholder",
        "canonical_storage_key": "characters/akira/v5/canonical_source.png",
        "status": "BLOCKED",
        "views": [],
        "quarantined": [],
        "contact_sheet_storage_key": "",
        "contact_sheet_content_hash": "",
    }
    (root / "view-pack.json").write_text(json.dumps(pack), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({"assets": []}), encoding="utf-8")
    (root / "brief.json").write_text(json.dumps(brief), encoding="utf-8")

    report = CharacterViewConsistencyReportService().build(
        pack_path=root / "view-pack.json",
        brief_path=root / "brief.json",
    )

    assert report["status"] == "BLOCKED_AUTOMATIC"
    assert "pack_complete" in report["automatic_blockers"]
