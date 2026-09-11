from __future__ import annotations

from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.trailer_director_service import TrailerDirectorService
from core.application.services.trailer_gate_service import TrailerGateService
from core.application.services.trailer_manifest_service import TrailerManifestService
from core.domain.value_objects.trailer_brief import TrailerBrief


def _plan():
    episode = EpisodeDirectorService().plan_text("SCENE: Rooftop\nAKIRA: We move now.")
    return TrailerDirectorService().plan(episode, TrailerBrief(trailer_id="gate-test"))


def test_placeholder_animatic_can_never_open_wan_gate():
    plan = _plan()
    manifest = TrailerManifestService().resolve(
        TrailerManifestService().build(plan), {}, strict=False
    )
    assert TrailerGateService.wan_test_status(
        plan, animatic_mode="PLACEHOLDER", manifest=manifest
    ) == "BLOCKED_PLACEHOLDER_ANIMATIC"


def test_strict_complete_frozen_trailer_can_open_wan_gate():
    plan = _plan()
    base = TrailerManifestService().build(plan)
    evidence = {
        asset["shot_id"]: {
            "start_keyframe": "frames/start.png",
            "background_clean": "backgrounds/clean.png",
            "character_reference": "characters/ref.png",
            "approval_receipts": ["receipt.json"],
            "prompt_hash": "p" * 64,                "workflow_hash": "w" * 64,
                "audio_hash": "a" * 64,

        }
        for asset in base.assets
    }
    manifest = TrailerManifestService().resolve(base, evidence, strict=True, freeze=True)
    assert TrailerGateService.wan_test_status(
        plan, animatic_mode="STRICT", manifest=manifest
    ) == "WAN_TEST_READY"
