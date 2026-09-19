from __future__ import annotations

import asyncio
import json

from core.application.services.asset_approval_service import AssetApprovalService
from core.application.services.episode_animatic_service import EpisodeAnimaticService
from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.location_bible_factory_service import LocationBibleFactoryService
from core.domain.value_objects.background_production import (
    BackgroundCandidate,
    BackgroundCandidatePack,
)
from infrastructure.providers.render.remotion_animatic_exporter import RemotionAnimaticExporter
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _location():
    return LocationBibleFactoryService().create(
        {
            "location_id": "rooftop",
            "name": "Rooftop",
            "description": "A rooftop above the city",
            "immutable_geometry": ["water tank"],
            "architecture": ["concrete ledge"],
            "palette": ["blue"],
            "lighting_sources": ["neon"],
            "weather_options": ["rain"],
            "style": "anime background",
        }
    )


def _plan(pack: BackgroundCandidatePack | None = None):
    return EpisodeDirectorService().plan_text(
        "SCENE: Rooftop\nAKIRA: We move now.",
        episode_id="animatic-test",
        locations=(_location(),),
        background_packs={"rooftop": pack} if pack else {},
    )


def test_episode_animatic_stays_planned_when_visual_or_audio_assets_are_missing(tmp_path):
    result = asyncio.run(
        EpisodeAnimaticService(LocalFsStorage(str(tmp_path))).build(_plan())
    )

    assert result.status == "BLOCKED"
    assert result.mode == "STRICT"
    assert result.project is None
    assert "animatic-test-shot-001:visual_asset" in result.missing_assets
    assert "animatic-test-shot-002:dialogue_audio" in result.missing_assets


def test_episode_animatic_placeholder_keeps_timeline_and_marks_missing_inputs(tmp_path):
    result = asyncio.run(
        EpisodeAnimaticService(LocalFsStorage(str(tmp_path))).build(
            _plan(), mode="PLACEHOLDER"
        )
    )

    assert result.status == "READY_FOR_REVIEW"
    assert result.mode == "PLACEHOLDER"
    assert result.project is not None
    assert result.project.duration_in_frames == 96
    assert result.project.clips[0].image_storage_key.startswith("placeholder://")
    assert result.project.clips[0].warning == "MISSING VISUAL ASSET"
    assert result.project.clips[1].warning == "MISSING VISUAL + DIALOGUE AUDIO"


def test_episode_animatic_builds_contiguous_24fps_project_and_remotion_props(tmp_path):
    storage = LocalFsStorage(str(tmp_path / "storage"))
    pack = BackgroundCandidatePack(
        location_id="rooftop",
        candidates=tuple(
            BackgroundCandidate(
                recipe_id=recipe_id,
                storage_key=f"backgrounds/rooftop/{recipe_id}.png",
                width=1344,
                height=768,
                attempt=1,
                content_hash="b" * 64,
            )
            for recipe_id in ("wide-01", "close-09")
        ),
    )
    receipt = AssetApprovalService.receipt(
        asset_id=pack.location_id,
        asset_hash=AssetApprovalService.asset_set_digest(
            [candidate.content_hash for candidate in pack.candidates]
        ),
        manifest_payload=pack.to_dict(),
        approved_by="art-director",
    )
    from dataclasses import replace
    pack = replace(pack, human_approved=True, approval_receipt=receipt.to_dict())
    plan = _plan(pack)
    audio_key = "audio/animatic-test-shot-002.wav"
    for requirement in plan.background_requirements:
        asyncio.run(storage.save(requirement.asset_ref, b"png-bytes", "image/png"))
    asyncio.run(storage.save(audio_key, b"wav-bytes", "audio/wav"))

    result = asyncio.run(
        EpisodeAnimaticService(storage).build(
            plan,
            dialogue_audio_keys={"animatic-test-shot-002": audio_key},
        )
    )

    assert result.status == "READY_FOR_REVIEW"
    assert result.project is not None
    assert result.project.fps == 24
    assert [clip.start_frame for clip in result.project.clips] == [0, 48]
    props_path = asyncio.run(
        RemotionAnimaticExporter(storage, tmp_path / "motion-public").export(
            result.project
        )
    )
    props = json.loads(props_path.read_text(encoding="utf-8"))
    assert props["fps"] == 24
    assert props["durationInFrames"] == result.project.duration_in_frames
    assert all("warning" in clip for clip in props["clips"])
    assert len(props["clips"]) == 2
    assert (props_path.parent / "animatic-test-shot-002.wav").is_file()
