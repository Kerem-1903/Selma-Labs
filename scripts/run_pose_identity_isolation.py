"""Isolate the pose guide from identity conditioning.

The pose pack keeps producing front-facing renders. Two explanations are
possible: the OpenPose guide does not reach the sampler, or identity
conditioning overrides it. This script answers that by rendering the same pose
twice -- once with the identity chain, once without -- and reporting what the
production QC detector sees.

Diagnostic only; it writes nothing into the production tree. Kept under 
scripts/ so the sweep that isolated identity strength as the dominant cause can 
be re-run from the repository instead of an ignored scratch directory.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

from config.container import create_container
from config.settings import get_settings
from core.domain.value_objects.production_infra import PreflightReport
from infrastructure.providers.keyframe.comfyui_keyframe_provider import (
    ComfyUIKeyframeProvider,
)
from infrastructure.providers.keyframe.comfyui_memory_releaser import (
    ComfyUiMemoryReleaser,
)
from core.application.services.character_pose_pack_service import (
    CharacterPosePackService,
)
from core.application.services.model_lock_service import load_model_lock
from infrastructure.providers.vision.ultralytics_character_view_detector import (
    UltralyticsCharacterViewDetector,
)

ROOT = Path(__file__).resolve().parents[1]
BRIEF = ROOT / "assets/character_creation_briefs/kaito.json"
APPROVAL = ROOT / "output/production/characters/kaito/v7/canonical-approval.json"
OUT = ROOT / "tmp/pose-guide-diagnosis"
POSES = ("PROFILE_LEFT", "BACK_FULL_BODY")


def detector() -> UltralyticsCharacterViewDetector:
    lock = load_model_lock(ROOT / "models.lock.json")
    root = Path(lock.comfyui_root)
    return UltralyticsCharacterViewDetector(
        face_model=str(root / lock.entry("face_detector").relative_path),
        pose_model=str(root / lock.entry("pose_detector").relative_path),
        confidence=0.35,
    )


def load_inputs():
    from cli.main import _load_character_creation_brief
    from core.domain.value_objects.character_design import CharacterCanonicalApproval

    brief = _load_character_creation_brief(BRIEF)
    approval = CharacterCanonicalApproval.from_dict(
        json.loads(APPROVAL.read_text(encoding="utf-8"))
    )
    return brief, approval


container = create_container(settings=get_settings())
releaser = ComfyUiMemoryReleaser(str(get_settings().comfyui_api_url))


class _NoPreflight:
    """The diagnostic renders back to back, so the once-per-instance preflight
    test job is replaced by freeing ComfyUI's RAM cache between renders."""

    def run(self, model_lock, full_hash):
        del model_lock, full_hash
        return PreflightReport(checks=())


_provider = ComfyUIKeyframeProvider(
    api_url=str(get_settings().comfyui_api_url),
    workflow_path=ROOT / get_settings().comfyui_keyframe_workflow_path,
    storage=container.keyframe_storage,
    model_lock=load_model_lock(ROOT / "models.lock.json"),
    preflight_service=_NoPreflight(),
)


async def main() -> int:
    brief, approval = load_inputs()
    assert approval.face_anchor is not None
    assert approval.fullbody_anchor is not None
    service = container.character_pose_pack_service
    det = detector()
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {}

    for pose_id in POSES:
        expected = dict(CharacterPosePackService._POSE_MATCH_VIEW)[pose_id]
        # The anchor pair, not the matched view: this sweep measures the identity
        # strength the isolation run identified as the dominant cause, and the
        # matched-view variant had already shown it drags its own framing in.
        base = service._build_request(
            brief,
            approval,
            style_key="series-style/selma-production-anime-v1/seed.png",
            style_hash="a" * 64,
            pose_id=pose_id,
            expected_view=expected,
            seed=4242,
            approved_view_pack=None,
        )
        base = replace(
            base,
            visual_constraints={
                **base.visual_constraints,
                "pose_strength": 1.0,
            },
        )
        def with_identity(weights, end_at):
            return replace(
                base,
                visual_constraints={
                    **base.visual_constraints,
                    "identity_reference_weights": list(weights),
                    "identity_end_at": end_at,
                },
            )

        variants = {
            "guide_only": replace(
                base,
                reference_asset_ids=(),
                reference_storage_keys=(),
                character_conditioning=(),
                visual_constraints={
                    key: value
                    for key, value in base.visual_constraints.items()
                    if key not in {"reference_views", "identity_reference_weights"}
                },
            ),
            "identity_075_050_end065": with_identity((0.75, 0.50), 0.65),
            "identity_045_030_end045": with_identity((0.45, 0.30), 0.45),
            "identity_025_015_end035": with_identity((0.25, 0.15), 0.35),
        }
        for label, request in variants.items():
            await releaser.release()
            generated = await _provider.generate_keyframe(request)
            path = OUT / f"{pose_id.casefold()}-{label}.png"
            path.write_bytes(generated.image_bytes)
            observation = await det.inspect(
                image_bytes=generated.image_bytes, expected_view=expected
            )
            entry = {
                "expected": expected,
                "provider": generated.metadata.get("provider") or _provider.name,
                "orientation": observation.orientation,
                "person_count": observation.person_count,
                "face_count": observation.face_count,
                "head_inside": observation.head_inside_frame,
                "feet_inside": observation.feet_inside_frame,
            }
            report.setdefault(pose_id, {})[label] = entry
            print(pose_id, label, json.dumps(entry))

    (OUT / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
