"""Build and freeze the explicit hash-bound asset checklist for every trailer shot."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from core.domain.value_objects.trailer_plan import TrailerPlan


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class TrailerAssetManifest:
    trailer_id: str
    assets: tuple[dict[str, Any], ...]
    status: str
    manifest_hash: str = ""
    frozen: bool = False

    @property
    def computed_hash(self) -> str:
        """Return the hash of the current in-memory evidence, not the stored claim."""
        return _digest(self.assets)

    def has_integrity(self) -> bool:
        """Detect mutation of a frozen manifest after its hash was recorded."""
        return bool(self.manifest_hash) and self.manifest_hash == self.computed_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "trailer_id": self.trailer_id,
            "status": self.status,
            "frozen": self.frozen,
            "manifest_hash": self.manifest_hash or self.computed_hash,
            "asset_count": len(self.assets),
            "assets": [dict(asset) for asset in self.assets],
        }


class TrailerManifestService:
    def build(self, plan: TrailerPlan) -> TrailerAssetManifest:
        assets = tuple(
            {
                "shot_id": shot.shot_id,
                "source_scene_id": shot.source_scene_id,
                "source_shot_id": shot.source_shot_id,
                "start_frame": shot.start_frame,
                "end_frame": shot.end_frame,
                "start_keyframe": "",
                "end_keyframe": "",
                "background_clean": "",
                "character_reference": "",
                "pose_reference": shot.pose_id,
                "dialogue": shot.dialogue,
                "system_voice": shot.system_voice,
                "music_cue": shot.music_cue,
                "sfx_cue": shot.sfx_cue,
                "prompt_hash": "",
                "workflow_hash": "",
                "audio_hash": "",
                "approval_receipts": [],
                "status": "PLANNED",
            }
            for shot in plan.shots
        )
        return TrailerAssetManifest(
            trailer_id=plan.timeline.trailer_id,
            assets=assets,
            status="PLANNED",
            manifest_hash=_digest(assets),
        )

    @staticmethod
    def resolve(
        manifest: TrailerAssetManifest,
        evidence: Mapping[str, Mapping[str, Any]],
        *,
        strict: bool = True,
        freeze: bool = False,
    ) -> TrailerAssetManifest:
        resolved: list[dict[str, Any]] = []
        blocked = False
        for asset in manifest.assets:
            item = dict(asset)
            proof = dict(evidence.get(str(item.get("shot_id", "")), {}))
            required = [
                "start_keyframe", "background_clean", "character_reference",
                "approval_receipts", "prompt_hash", "workflow_hash",
            ]
            if item.get("dialogue") or item.get("system_voice"):
                required.append("audio_hash")
            complete = all(proof.get(field) for field in required)
            item.update(proof)
            item["status"] = "READY" if complete else ("BLOCKED" if strict else "PLACEHOLDER")
            blocked = blocked or not complete
            resolved.append(item)
        status = "BLOCKED" if blocked and strict else ("PLACEHOLDER" if blocked else "READY")
        frozen = freeze and status == "READY"
        assets = tuple(resolved)
        return TrailerAssetManifest(
            trailer_id=manifest.trailer_id,
            assets=assets,
            status=status,
            frozen=frozen,
            manifest_hash=_digest(assets),
        )
