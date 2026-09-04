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


def test_audit_blocks_caption_that_contradicts_face_view(tmp_path):
    (tmp_path / "train").mkdir()
    (tmp_path / "train/sample.png").write_bytes(b"image")
    (tmp_path / "train/sample.txt").write_text("caption", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "character_id": "akira",
                "dataset_complete": True,
                "training_approved": True,
                "is_ready": True,
                "anchor_content_hash": "anchor",
                "approved_by": "Kerem",
                "samples": [
                    {
                        "view": "FACE_CLOSEUP",
                        "caption": "selma_akira_v2, face close-up, full body, knee pads",
                        "image_path": "train/sample.png",
                        "caption_path": "train/sample.txt",
                        "review": {"passed": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    audit = CharacterLoraDatasetAuditService().audit(manifest)

    assert audit.training_approved is False
    assert "caption_view_mismatch" in audit.blockers
