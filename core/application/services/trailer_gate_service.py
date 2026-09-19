"""Release gates for trailer animation handoff."""

from __future__ import annotations

from typing import Any

from core.application.services.trailer_manifest_service import TrailerAssetManifest
from core.domain.value_objects.trailer_plan import TrailerPlan


class TrailerGateService:
    """Own the distinction between reviewable animatic and WAN-ready package."""

    @staticmethod
    def wan_test_status(
        plan: TrailerPlan,
        *,
        animatic_mode: str,
        manifest: TrailerAssetManifest,
    ) -> str:
        if animatic_mode != "STRICT":
            return "BLOCKED_PLACEHOLDER_ANIMATIC"
        if manifest.status != "READY" or not manifest.frozen:
            return "BLOCKED_ASSET_APPROVAL"
        if not manifest.has_integrity():
            return "BLOCKED_MANIFEST_HASHES"
        if not manifest.manifest_hash or any(
            not asset.get("prompt_hash") or not asset.get("workflow_hash")
            for asset in manifest.assets
        ):
            return "BLOCKED_MANIFEST_HASHES"
        if plan.timeline.fps != 24 or plan.timeline.duration_frames != 4320:
            return "BLOCKED_TIMELINE"
        return "WAN_TEST_READY"

    @staticmethod
    def report(plan: TrailerPlan, **kwargs: Any) -> dict[str, Any]:
        status = TrailerGateService.wan_test_status(plan, **kwargs)
        manifest = kwargs["manifest"]
        return {
            "status": status,
            "wan_test_ready": status == "WAN_TEST_READY",
            "trailer_id": plan.timeline.trailer_id,
            "fps": plan.timeline.fps,
            "duration_frames": plan.timeline.duration_frames,
            "manifest_hash": manifest.manifest_hash,
        }
