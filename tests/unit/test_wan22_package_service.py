from __future__ import annotations

import hashlib
import json
import sys

import pytest

from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.trailer_director_service import TrailerDirectorService
from core.application.services.wan22_package_service import Wan22PackageService
from core.domain.value_objects.trailer_brief import TrailerBrief
from core.domain.value_objects.wan22_render_profile import Wan22RenderProfile


def _plan():
    episode = EpisodeDirectorService().plan_text(
        "SCENE: Rooftop\nAKIRA: We move now."
    )
    return TrailerDirectorService().plan(episode, TrailerBrief(trailer_id="trailer"))


def test_wan_package_requires_every_shot_source_and_preserves_traceability():
    plan = _plan()
    digest = "a" * 64
    sources = {
        shot.shot_id: {
            "source_image_key": f"storyboards/{shot.shot_id}.png",
            "source_image_hash": digest,
            "motion_prompt": "slow cinematic push in",
        }
        for shot in plan.shots
    }
    packages = Wan22PackageService().build(plan, sources)
    assert len(packages) == len(plan.shots)
    assert packages[0].frame_count == plan.shots[0].duration_frames
    assert packages[0].fps == 24
    assert packages[0].source_image_hash == digest
    assert packages[0].output_video_key == f"wan22/{packages[0].shot_id}.mp4"


def test_wan_worker_preflight_is_blocked_until_real_worker_is_configured(tmp_path):
    config = tmp_path / "worker.json"
    config.write_text(json.dumps({"status": "UNCONFIGURED", "vram_gb": 80}), encoding="utf-8")
    result = Wan22PackageService.preflight(config)
    assert result["status"] == "BLOCKED"
    assert "container_image" in result["missing_configuration"]


def test_wan_package_rejects_missing_source():
    with pytest.raises(ValueError):
        Wan22PackageService().build(_plan(), {})


def test_wan_package_uses_explicit_draft_generation_contract():
    plan = _plan()
    sources = {
        shot.shot_id: {
            "source_image_key": f"storyboards/{shot.shot_id}.png",
            "source_image_hash": "a" * 64,
            "motion_prompt": "move",
        }
        for shot in plan.shots
    }
    package = Wan22PackageService().build(
        plan, sources, render_profile=Wan22RenderProfile.draft_16fps()
    )[0]
    assert (package.frame_count, package.fps) == (81, 16)


def test_wan_worker_preflight_checks_hashes_runtime_volume_and_auto_stop(tmp_path):
    digest = hashlib.sha256(b"pinned").hexdigest()
    models = {}
    for name in ("high_noise", "low_noise", "vae", "umt5"):
        model = tmp_path / f"{name}.bin"
        model.write_bytes(b"pinned")
        models[name] = {"path": model.name, "sha256": digest}
    workflow = tmp_path / "workflow.json"
    workflow.write_bytes(b"pinned")
    volume = tmp_path / "volume"
    volume.mkdir()
    config = tmp_path / "ready-worker.json"
    config.write_text(
        json.dumps(
            {
                "status": "READY",
                "provider": "fake",
                "container_image": "wan@sha256:pinned",
                "model_revision": "pinned",
                "persistent_storage": {"type": "volume", "path": str(volume)},
                "model_files": models,
                "workflow_path": workflow.name,
                "workflow_hash": digest,
                "provider_auto_stop_enabled": True,
                "ffmpeg_binary": sys.executable,
                "ffprobe_binary": sys.executable,
                "vram_gb": 80,
                "minimum_vram_gb": 48,
            }
        ),
        encoding="utf-8",
    )
    result = Wan22PackageService.preflight(config)
    assert result["status"] == "READY"
    assert result["preflight_errors"] == []
