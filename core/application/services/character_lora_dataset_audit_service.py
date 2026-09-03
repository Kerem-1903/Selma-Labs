from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


@dataclass(frozen=True)
class CharacterLoraDatasetAudit:
    character_id: str
    schema_version: int
    dataset_complete: bool
    training_approved: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "schema_version": self.schema_version,
            "dataset_complete": self.dataset_complete,
            "training_approved": self.training_approved,
            "blockers": list(self.blockers),
            "next_gate": (
                "LORA_TRAINING" if self.training_approved else "DATASET_REVIEW"
            ),
        }


class CharacterLoraDatasetAuditService:
    """Fail-closed audit for existing and newly generated LoRA manifests."""

    def audit(self, manifest_path: str | Path) -> CharacterLoraDatasetAudit:
        path = Path(manifest_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        samples = payload.get("samples")
        if not isinstance(samples, list):
            raise TypeError("LoRA dataset manifest requires a samples array.")

        blockers: list[str] = []
        schema_version = int(payload.get("schema_version", 0))
        if schema_version < 2:
            blockers.append("legacy_manifest_requires_v2_rebuild")
        if not bool(payload.get("dataset_complete", payload.get("is_ready", False))):
            blockers.append("dataset_incomplete")
        if not self._text(payload.get("anchor_content_hash")):
            blockers.append("canonical_anchor_missing")
        if not self._text(payload.get("approved_by")):
            blockers.append("dataset_approver_missing")

        dataset_root = path.parent.resolve()
        for sample in samples:
            if not isinstance(sample, dict):
                blockers.append("invalid_sample_entry")
                continue
            for key in ("image_path", "caption_path"):
                raw_relative = str(sample.get(key, ""))
                relative = PurePosixPath(raw_relative.replace("\\", "/"))
                if (
                    not raw_relative
                    or relative.is_absolute()
                    or any(part in {"", ".", ".."} for part in relative.parts)
                    or not (dataset_root / Path(*relative.parts)).is_file()
                ):
                    blockers.append("sample_asset_missing_or_unsafe")
                    break
            review = sample.get("review")
            if not isinstance(review, dict):
                blockers.append("sample_reviews_missing")
            elif review.get("passed") is not True:
                blockers.append("sample_reviews_failed")

        unique_blockers = tuple(dict.fromkeys(blockers))
        training_approved = (
            not unique_blockers
            and payload.get("training_approved") is True
            and payload.get("is_ready") is True
        )
        if not training_approved and not unique_blockers:
            unique_blockers = ("manifest_not_marked_training_approved",)
        return CharacterLoraDatasetAudit(
            character_id=str(payload.get("character_id", "")),
            schema_version=schema_version,
            dataset_complete=bool(
                payload.get("dataset_complete", payload.get("is_ready", False))
            ),
            training_approved=training_approved,
            blockers=unique_blockers,
        )

    def create_review_template(
        self, *, manifest_path: str | Path, canonical_anchor: str | Path
    ) -> dict[str, Any]:
        payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        samples = payload.get("samples")
        if not isinstance(samples, list) or not samples:
            raise ValueError("LoRA manifest has no samples to review.")
        anchor = Path(canonical_anchor)
        if not anchor.is_file():
            raise FileNotFoundError(f"Canonical identity anchor not found: {anchor}")
        reviews: dict[str, dict[str, object]] = {}
        for sample in samples:
            if not isinstance(sample, dict):
                raise TypeError("LoRA manifest contains an invalid sample entry.")
            source_name = self._text(sample.get("source_name"))
            content_hash = self._text(sample.get("content_hash"))
            if not source_name or not content_hash:
                raise ValueError("LoRA sample is missing source identity data.")
            reviews[source_name] = {
                "identity_score": 0.0,
                "anatomy_score": 0.0,
                "caption_matches": False,
                "human_approved": False,
                "reviewer": "",
                "content_hash": content_hash,
                "notes": "pending review",
            }
        return {
            "schema_version": 1,
            "character_id": self._text(payload.get("character_id")),
            "approved_by": "",
            "canonical_anchor_sha256": hashlib.sha256(anchor.read_bytes()).hexdigest(),
            "reviews": reviews,
        }

    @staticmethod
    def _text(value: object) -> str:
        return value.strip() if isinstance(value, str) else ""
