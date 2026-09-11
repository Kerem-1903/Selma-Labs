from __future__ import annotations

import hashlib
import json

from core.application.services.anime_production_readiness_service import (
    ANIMATION,
    VISUAL,
    AnimeProductionReadinessService,
)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_visual_readiness_fails_closed_on_unapproved_style_and_empty_cast(tmp_path):
    style = tmp_path / "style.png"
    style.write_bytes(b"style")
    _write_json(
        tmp_path / "requirements.json",
        {
            "required_tools": [],
            "required_model_roles": [],
            "required_workflows": [],
        },
    )
    _write_json(
        tmp_path / "series.json",
        {
            "schema_version": 1,
            "series_id": "series-one",
            "title": "Series One",
            "style_bible": {
                "style_id": "style-one",
                "reference_asset": "style.png",
                "reference_sha256": hashlib.sha256(b"style").hexdigest(),
                "width": 1,
                "height": 1,
                "status": "PROVISIONAL",
                "rendering_rules": ["rule"],
                "composition_rules": ["rule"],
                "identity_policy": ["rule"],
            },
            "character_registry": "cast.json",
            "model_lock": "models.lock.json",
            "production_root": "output/series-one",
            "style_approval_receipt": "approval.json",
            "production_style_lock": "lock.json",
        },
    )
    _write_json(
        tmp_path / "cast.json",
        {"schema_version": 1, "series_id": "series-one", "members": []},
    )
    _write_json(
        tmp_path / "models.lock.json",
        {"schema_version": 1, "comfyui_root": str(tmp_path), "models": []},
    )

    report = AnimeProductionReadinessService(tmp_path).evaluate(
        VISUAL,
        series_project="series.json",
        requirements_path="requirements.json",
    )

    assert report.ready is False
    assert {check.name for check in report.failures} >= {
        "approved_style",
        "style_approval_receipt",
        "production_style_lock",
        "canonical_cast",
    }


def test_animation_readiness_lists_worker_and_episode_package_blockers(tmp_path):
    _write_json(
        tmp_path / "requirements.json",
        {
            "required_local_tools": [],
            "model": {
                "repository": "Wan-AI/Wan2.2-I2V-A14B",
                "minimum_vram_gb": 80,
            },
            "required_remote_worker_file": "worker.json",
            "required_episode_files": ["animatic.mp4", "wan-render-manifest.json"],
            "required_episode_directories": ["keyframes"],
            "required_shot_fields": ["shot_id", "production_method"],
            "allowed_production_methods": ["WAN_I2V"],
        },
    )

    report = AnimeProductionReadinessService(tmp_path).evaluate(
        ANIMATION,
        requirements_path="requirements.json",
    )

    assert report.ready is False
    assert {check.name for check in report.failures} >= {
        "remote_worker",
        "episode_package",
    }


def test_animation_readiness_accepts_complete_minimal_package(tmp_path):
    _write_json(
        tmp_path / "requirements.json",
        {
            "required_local_tools": [],
            "model": {
                "repository": "Wan-AI/Wan2.2-I2V-A14B",
                "minimum_vram_gb": 80,
            },
            "required_remote_worker_file": "worker.json",
            "required_episode_files": ["animatic.mp4", "wan-render-manifest.json"],
            "required_episode_directories": ["keyframes"],
            "required_shot_fields": ["shot_id", "production_method"],
            "allowed_production_methods": ["WAN_I2V"],
        },
    )
    _write_json(
        tmp_path / "worker.json",
        {
            "status": "READY",
            "vram_gb": 80,
            "model_repository": "Wan-AI/Wan2.2-I2V-A14B",
            "model_revision": "pinned-revision",
            "container_image": "registry/image@sha256:digest",
            "persistent_storage": "/workspace/models",
        },
    )
    episode = tmp_path / "episode"
    episode.mkdir()
    (episode / "animatic.mp4").write_bytes(b"video")
    _write_json(
        episode / "wan-render-manifest.json",
        {"shots": [{"shot_id": "s1", "production_method": "WAN_I2V"}]},
    )
    (episode / "keyframes").mkdir()
    (episode / "keyframes" / "s1.png").write_bytes(b"image")

    report = AnimeProductionReadinessService(tmp_path).evaluate(
        ANIMATION,
        episode_root=episode,
        requirements_path="requirements.json",
    )

    assert report.ready is True
