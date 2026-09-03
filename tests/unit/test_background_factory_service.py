from __future__ import annotations

import asyncio

from core.application.services.background_factory_service import (
    BackgroundFactoryService,
)
from core.application.services.location_bible_factory_service import (
    LocationBibleFactoryService,
)
from core.domain.value_objects.generated_depth_map import GeneratedDepthMap
from core.domain.value_objects.preproduction_image_quality import (
    PreproductionImageQuality,
)
from infrastructure.providers.keyframe.fake_keyframe_generation_provider import (
    FakeKeyframeGenerationProvider,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _location():
    return LocationBibleFactoryService().create(
        {
            "location_id": "rain-station",
            "name": "Rain Station",
            "description": "An elevated abandoned railway platform",
            "immutable_geometry": ["two parallel tracks", "central clock tower"],
            "architecture": ["weathered concrete", "steel canopy"],
            "palette": ["blue grey", "amber"],
            "lighting_sources": ["platform lamps"],
            "interaction_points": ["bench", "stair entrance"],
            "weather_options": ["rain"],
            "forbidden_elements": ["modern advertising"],
            "style": "cinematic hand-painted anime background",
        }
    )


def test_background_plan_has_clean_twelve_shot_coverage():
    plan = BackgroundFactoryService.plan(_location())

    assert len(plan.recipes) == 12
    assert {item.shot_scale for item in plan.recipes} == {
        "wide establishing",
        "medium",
        "close detail",
    }
    assert "person" in plan.negative_prompts
    assert all("empty scene" in item.prompt for item in plan.recipes)
    assert plan.depth_map_required is True


class _PassEvaluator:
    async def evaluate(self, **kwargs):
        assert kwargs["reference_bytes"] is None
        assert kwargs["subject_policy"] == "character_forbidden"
        return PreproductionImageQuality(
            score=0.9,
            threshold=0.72,
            passed=True,
            identity_or_geometry_score=0.85,
            composition_score=0.9,
            subject_policy_score=1.0,
            confidence=0.9,
            provider="fake:vision",
        )


def test_background_generation_is_unapproved_and_character_free(tmp_path):
    provider = FakeKeyframeGenerationProvider()
    service = BackgroundFactoryService(
        provider, LocalFsStorage(str(tmp_path)), _PassEvaluator()
    )

    pack = asyncio.run(service.generate(_location()))

    assert pack.human_approved is False
    assert len(pack.candidates) == 12
    assert all(not item.parallax_ready for item in pack.candidates)
    assert all("/source/" in item.storage_key for item in pack.candidates)
    assert all(request.character_conditioning == () for request in provider.requests)
    assert all("person" in request.negative_prompts for request in provider.requests)


class _DepthMapper:
    async def generate_depth_map(self, image_bytes):
        return GeneratedDepthMap(
            image_bytes=image_bytes,
            content_type="image/png",
            width=1344,
            height=768,
            provider_asset_id="fake-depth",
        )


def test_background_becomes_parallax_ready_only_after_real_depth_artifact(tmp_path):
    service = BackgroundFactoryService(
        FakeKeyframeGenerationProvider(),
        LocalFsStorage(str(tmp_path)),
        _PassEvaluator(),
        _DepthMapper(),
    )

    pack = asyncio.run(service.generate(_location()))

    assert all(item.parallax_ready for item in pack.candidates)
    assert all(item.depth_map_storage_key for item in pack.candidates)
    assert all(
        (tmp_path / str(item.depth_map_storage_key)).is_file()
        for item in pack.candidates
    )
