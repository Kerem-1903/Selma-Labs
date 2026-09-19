"""Build and score a human-labelled character QC calibration set."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCORE_FIELDS = (
    "identity_similarity",
    "anatomy",
    "style",
    "costume",
    "artifacts",
)
_DECISIONS = {"ACCEPT", "REJECT"}


class CharacterQcCalibrationService:
    """Keep automatic QC evidence separate from later human judgements."""

    def create_manifest(
        self,
        *,
        storage_root: str | Path,
        benchmark_prefix: str,
        minimum_images: int = 50,
        maximum_images: int = 100,
    ) -> dict[str, Any]:
        root = Path(storage_root).resolve()
        prefix = self._portable_prefix(benchmark_prefix)
        if minimum_images < 1 or maximum_images < minimum_images:
            raise ValueError("Calibration image bounds are invalid.")
        image_paths = sorted(
            path
            for path in (root / prefix).rglob("*.png")
            if path.is_file()
            and ("candidates" in path.parts or "quarantine" in path.parts)
        )
        selected = self._balanced_sample(
            image_paths,
            root=root,
            prefix=prefix,
            maximum_images=maximum_images,
        )
        items = [
            self._item(path, root=root, prefix=prefix)
            for path in selected
        ]
        return {
            "schema_version": 1,
            "status": "PENDING_HUMAN_REVIEW",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "benchmark_prefix": prefix,
            "minimum_images": minimum_images,
            "maximum_images": maximum_images,
            "sample_count": len(items),
            "sample_sufficient": len(items) >= minimum_images,
            "review_instructions": {
                "decision": "Set human_review.decision to ACCEPT or REJECT; never copy automatic_qc into this field.",
                "scores": "Score each field from 1 (fail) to 5 (production-ready).",
                "required_scores": list(_SCORE_FIELDS),
                "reviewer": "Record the human reviewer name and review timestamp.",
            },
            "items": items,
        }

    def summarize(self, manifest: dict[str, Any]) -> dict[str, Any]:
        items = manifest.get("items")
        if not isinstance(items, list):
            raise ValueError("Calibration manifest must contain an items list.")
        reviewed = [item for item in items if self._is_reviewed(item)]
        pending = len(items) - len(reviewed)
        result: dict[str, Any] = {
            "schema_version": 1,
            "status": "COMPLETE" if not pending else "PENDING_HUMAN_REVIEW",
            "sample_count": len(items),
            "reviewed_count": len(reviewed),
            "pending_count": pending,
            "false_accepts": None,
            "false_rejects": None,
            "false_accept_rate": None,
            "false_reject_rate": None,
            "average_scores": None,
        }
        if pending or not reviewed:
            return result
        false_accepts = sum(
            1
            for item in reviewed
            if item["automatic_qc"]["passed"]
            and item["human_review"]["decision"] == "REJECT"
        )
        false_rejects = sum(
            1
            for item in reviewed
            if not item["automatic_qc"]["passed"]
            and item["human_review"]["decision"] == "ACCEPT"
        )
        result["false_accepts"] = false_accepts
        result["false_rejects"] = false_rejects
        result["false_accept_rate"] = round(false_accepts / len(reviewed), 4)
        result["false_reject_rate"] = round(false_rejects / len(reviewed), 4)
        result["average_scores"] = {
            field: round(
                sum(item["human_review"]["scores"][field] for item in reviewed)
                / len(reviewed),
                3,
            )
            for field in _SCORE_FIELDS
        }
        return result

    @staticmethod
    def _portable_prefix(value: str) -> str:
        prefix = value.replace("\\", "/").strip("/")
        if not prefix or any(part in {"", ".", ".."} for part in prefix.split("/")):
            raise ValueError("Calibration benchmark_prefix must stay inside storage root.")
        return prefix

    @classmethod
    def _balanced_sample(
        cls,
        paths: list[Path],
        *,
        root: Path,
        prefix: str,
        maximum_images: int,
    ) -> list[Path]:
        if len(paths) <= maximum_images:
            return paths
        groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
        for path in paths:
            item = cls._item(path, root=root, prefix=prefix)
            groups[(item["model_variant"], item["source_kind"])].append(path)
        selected: list[Path] = []
        while len(selected) < maximum_images and groups:
            for key in sorted(tuple(groups)):
                bucket = groups.get(key)
                if not bucket:
                    groups.pop(key, None)
                    continue
                selected.append(bucket.pop(0))
                if len(selected) == maximum_images:
                    break
        return selected

    @classmethod
    def _item(cls, path: Path, *, root: Path, prefix: str) -> dict[str, Any]:
        storage_key = path.relative_to(root).as_posix()
        relative = path.relative_to(root / prefix).parts
        source_kind = "quarantine" if "quarantine" in relative else "candidate"
        model_variant = relative[1] if len(relative) > 1 else "unknown"
        character_id = "unknown"
        if model_variant in relative:
            index = relative.index(model_variant)
            if len(relative) > index + 1:
                character_id = relative[index + 1]
        automatic = cls._automatic_qc(path, root=root)
        return {
            "item_id": "qc-" + hashlib.sha256(storage_key.encode("utf-8")).hexdigest()[:16],
            "image_storage_key": storage_key,
            "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "character_id": character_id,
            "model_variant": model_variant,
            "source_kind": source_kind,
            "automatic_qc": automatic,
            "human_review": {
                "decision": None,
                "scores": {field: None for field in _SCORE_FIELDS},
                "reviewer": "",
                "reviewed_at": "",
                "notes": "",
            },
        }

    @staticmethod
    def _automatic_qc(path: Path, *, root: Path) -> dict[str, Any]:
        relative_key = path.relative_to(root).as_posix()
        for manifest_path in path.parents:
            manifest = manifest_path / "run-manifest.json"
            if not manifest.is_file():
                continue
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                break
            for attempt in payload.get("attempts", []):
                if not isinstance(attempt, dict) or attempt.get("storage_key") != relative_key:
                    continue
                report = attempt.get("qc_report", {})
                return {
                    "passed": attempt.get("state") == "QC_PASSED",
                    "state": attempt.get("state", "UNKNOWN"),
                    "reasons": list(report.get("reasons", [])) if isinstance(report, dict) else [],
                    "checks": dict(report.get("checks", {})) if isinstance(report, dict) else {},
                }
            break
        return {"passed": "quarantine" not in path.parts, "state": "UNKNOWN", "reasons": [], "checks": {}}

    @staticmethod
    def _is_reviewed(item: Any) -> bool:
        if not isinstance(item, dict):
            return False
        review = item.get("human_review")
        if not isinstance(review, dict) or review.get("decision") not in _DECISIONS:
            return False
        scores = review.get("scores")
        return (
            isinstance(scores, dict)
            and all(isinstance(scores.get(field), int) and 1 <= scores[field] <= 5 for field in _SCORE_FIELDS)
            and bool(str(review.get("reviewer", "")).strip())
            and bool(str(review.get("reviewed_at", "")).strip())
        )
