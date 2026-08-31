import pytest
from unittest.mock import AsyncMock
from core.application.services.shot_production_service import ShotProductionService
from core.domain.entities.shot_contract import ShotContract
from core.domain.value_objects.shot_constraints import CameraConstraints, ActionConstraints, VisualConstraints
from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.render_profile import RenderProfile

@pytest.fixture
def mock_generator():
    gen = AsyncMock()
    return gen

@pytest.fixture
def contract():
    return ShotContract(
        id="shot-01",
        camera_constraints=CameraConstraints(angle="wide", lens="35mm", movement="static"),
        action_constraints=ActionConstraints(primary_action="walking"),
        visual_constraints=VisualConstraints(lighting="dark", environment_style="anime", weather="rain")
    )

@pytest.mark.asyncio
async def test_produce_shot_success(mock_generator, contract):
    mock_asset = MediaAsset(id="1", provider="mock", original_url="mock.mp4", duration_seconds=5.0)
    mock_generator.generate_video.return_value = mock_asset

    service = ShotProductionService(video_generator=mock_generator)
    result = await service.produce_shot(contract, target_duration=5.0, profile=RenderProfile.DRAFT)

    assert result == mock_asset
    assert service.get_shot_cost("shot-01") == 1
    mock_generator.generate_video.assert_called_once()

    req = mock_generator.generate_video.call_args[0][0]
    assert req.shot_contract_id == "shot-01"
    assert req.render_profile == RenderProfile.DRAFT

@pytest.mark.asyncio
async def test_produce_shot_retry_success(mock_generator, contract):
    mock_asset = MediaAsset(id="1", provider="mock", original_url="mock.mp4", duration_seconds=5.0)
    # Fail first time, succeed second time
    mock_generator.generate_video.side_effect = [Exception("API error"), mock_asset]

    service = ShotProductionService(video_generator=mock_generator, max_retries=1)
    result = await service.produce_shot(contract, target_duration=5.0)

    assert result == mock_asset
    assert service.get_shot_cost("shot-01") == 2
    assert mock_generator.generate_video.call_count == 2

@pytest.mark.asyncio
async def test_produce_shot_exhaust_retries(mock_generator, contract):
    mock_generator.generate_video.side_effect = Exception("API error")

    service = ShotProductionService(video_generator=mock_generator, max_retries=2)

    with pytest.raises(RuntimeError, match="Shot production failed after 2 retries"):
        await service.produce_shot(contract, target_duration=5.0)

    assert service.get_shot_cost("shot-01") == 3
    assert mock_generator.generate_video.call_count == 3
