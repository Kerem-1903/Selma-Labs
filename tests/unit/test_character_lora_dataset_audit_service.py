from __future__ import annotations

import json

from core.application.services.character_lora_dataset_audit_service import (
    CharacterLoraDatasetAuditService,
)


def test_audit_blocks_legacy_count_only_manifest(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "character_id": "akira",
                "is_ready": True,
                "samples": [],
            }
        ),
        encoding="utf-8",
    )

    audit = CharacterLoraDatasetAuditService().audit(manifest)

    assert audit.training_approved is False
    assert "legacy_manifest_requires_v2_rebuild" in audit.blockers
    assert "canonical_anchor_missing" in audit.blockers


def test_service_creates_fail_closed_review_template(tmp_path):
    anchor = tmp_path / "anchor.png"
    anchor.write_bytes(b"approved-anchor")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "character_id": "akira",
                "samples": [
                    {
                        "source_name": "front.png",
                        "content_hash": "abc123",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    template = CharacterLoraDatasetAuditService().create_review_template(
        manifest_path=manifest, canonical_anchor=anchor
    )

    assert template["character_id"] == "akira"
    assert template["approved_by"] == ""
    assert template["reviews"]["front.png"]["human_approved"] is False
    assert template["reviews"]["front.png"]["content_hash"] == "abc123"
