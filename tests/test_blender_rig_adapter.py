import json
from unittest.mock import AsyncMock, patch

import pytest

from core.domain.exceptions import BlenderExecutionError
from infrastructure.providers.blender.blender_rig_adapter import BlenderRigAdapter


@pytest.fixture
def adapter() -> BlenderRigAdapter:
    with patch(
        "infrastructure.providers.blender.blender_rig_adapter.BlenderBinaryResolver.resolve",
        return_value="/mock/blender",
    ):
        return BlenderRigAdapter()


@pytest.mark.asyncio
async def test_validate_rig_parses_immutable_report(adapter, tmp_path):
    model = tmp_path / "akira.blend"
    model.touch()
    payload = {
        "is_valid": False,
        "errors": ["No armature found."],
        "shape_keys": [],
        "available_actions": [],
    }
    adapter._run_headless_script = AsyncMock(
        return_value=(
            f"Blender output\n###JSON_START###\n{json.dumps(payload)}\n###JSON_END###\n"
        )
    )

    report = await adapter.validate_rig(str(model))

    assert report.is_valid is False
    assert report.errors == ("No armature found.",)


@pytest.mark.asyncio
async def test_validate_rig_rejects_missing_or_non_blend_models(adapter, tmp_path):
    with pytest.raises(BlenderExecutionError, match="not found"):
        await adapter.validate_rig(str(tmp_path / "missing.blend"))

    model = tmp_path / "akira.fbx"
    model.touch()
    with pytest.raises(BlenderExecutionError, match="requires a .blend"):
        await adapter.validate_rig(str(model))


@pytest.mark.asyncio
async def test_preview_requires_exact_refreshed_mp4(adapter, tmp_path):
    model = tmp_path / "akira.blend"
    model.touch()
    output = tmp_path / "preview.mp4"

    async def render(args):
        output.write_bytes(b"new-video")
        return ""

    adapter._run_headless_script = render

    result = await adapter.bake_action_preview(
        str(model), "IDLE_BREATHING", str(output)
    )

    assert result == str(output.resolve())
    assert output.read_bytes() == b"new-video"


@pytest.mark.asyncio
async def test_preview_rejects_wrong_extension(adapter, tmp_path):
    model = tmp_path / "akira.blend"
    model.touch()

    with pytest.raises(BlenderExecutionError, match=".mp4"):
        await adapter.bake_action_preview(
            str(model), "IDLE_BREATHING", str(tmp_path / "preview.mov")
        )
