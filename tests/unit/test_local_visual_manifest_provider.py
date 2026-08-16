from __future__ import annotations

import json

import pytest

from core.domain.value_objects.visual_intent import VisualIntent
from infrastructure.providers.video.local_visual_manifest_provider import (
    LocalVisualManifestProvider,
)


def _intent(start_ms: int, end_ms: int) -> VisualIntent:
    return VisualIntent(
        primary_keyword="venus",
        mood="mysterious",
        motion_type="steady",
        start_ms=start_ms,
        end_ms=end_ms,
        visual_job="support_context",
    )


def test_local_visual_manifest_requires_explicit_approval(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"synthetic-video")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "operator_approved": False,
        "assets": [{
            "file": clip.name,
            "attribution": "Project generator",
            "license": "Original project asset",
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="operator_approved=true"):
        LocalVisualManifestProvider(manifest).select([_intent(0, 1_000)])


def test_local_visual_manifest_maps_unique_licensed_clips_to_intents(tmp_path):
    entries = []
    for index in range(2):
        clip = tmp_path / f"clip-{index}.mp4"
        clip.write_bytes(f"synthetic-video-{index}".encode())
        entries.append({
            "id": f"owned:{index}",
            "file": clip.name,
            "provider": "local-procedural",
            "attribution": "Project generator",
            "license": "Original project asset",
            "motion_energy": 0.62,
        })
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "operator_approved": True,
        "assets": entries,
    }), encoding="utf-8")

    assets, usages = LocalVisualManifestProvider(manifest).select([
        _intent(0, 1_000),
        _intent(1_000, 2_000),
    ])

    assert [asset.id for asset in assets] == ["owned:0", "owned:1"]
    assert all(asset.metadata["operator_approved"] for asset in assets)
    assert [usage.start_ms for usage in usages] == [0, 1_000]
    assert all(usage.motion_energy == 0.62 for usage in usages)


def test_local_visual_manifest_blocks_path_traversal(tmp_path):
    outside = tmp_path.parent / "outside.mp4"
    outside.write_bytes(b"outside")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "operator_approved": True,
        "assets": [{
            "file": "../outside.mp4",
            "attribution": "Project generator",
            "license": "Original project asset",
        }],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="escapes the manifest directory"):
        LocalVisualManifestProvider(manifest).select([_intent(0, 1_000)])
