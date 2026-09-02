import pytest
from PIL import Image
from unittest.mock import AsyncMock

from core.application.services.multiview_asset_registration_service import MultiviewAssetRegistrationService
from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.character_identity import ReferenceView

@pytest.fixture
def dummy_image(tmp_path):
    img = Image.new('RGB', (500, 100), color = 'red')
    img_path = tmp_path / "test_multiview.png"
    img.save(img_path)
    return str(img_path)

@pytest.mark.asyncio
async def test_register_multiview_asset(dummy_image):
    storage_mock = AsyncMock()
    service = MultiviewAssetRegistrationService(storage=storage_mock)
    bible = CharacterBible.akira()

    updated_bible = await service.register_multiview_asset(bible, dummy_image)

    # Check that 5 slices were saved to storage
    assert storage_mock.save.call_count == 5

    # Check that CharacterBible reference_pack was populated
    assert len(updated_bible.reference_pack) == 5

    assert ReferenceView.FRONT in updated_bible.reference_pack
    assert updated_bible.reference_pack[ReferenceView.FRONT].storage_key == "characters/akira/views/v1/front.png"

    assert ReferenceView.FACE_CLOSEUP in updated_bible.reference_pack

def test_register_multiview_asset_invalid_size(tmp_path):
    img = Image.new('RGB', (2, 2), color = 'red') # Too small for 5 views
    img_path = tmp_path / "small.png"
    img.save(img_path)

    service = MultiviewAssetRegistrationService(storage=AsyncMock())
    bible = CharacterBible.akira()

    with pytest.raises(ValueError, match="is too small to contain 5 views"):
        import asyncio
        asyncio.run(service.register_multiview_asset(bible, str(img_path)))
