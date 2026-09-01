import json
import pytest
from unittest import mock
from unittest.mock import AsyncMock

from infrastructure.providers.blender.blender_scene_adapter import BlenderSceneAdapter
from core.domain.value_objects.blender_render_manifest import BlenderRenderManifest

@pytest.fixture
def mock_blender_binary():
    with mock.patch("infrastructure.providers.blender.blender_scene_adapter.BlenderBinaryResolver.resolve", return_value="/mock/blender"):
        yield

@pytest.mark.asyncio
async def test_render_turntable_success(mock_blender_binary, tmp_path):
    adapter = BlenderSceneAdapter()

    mock_process = AsyncMock()
    mock_process.returncode = 0
    mock_process.communicate.return_value = (b"", b"")

    # Mock the manifest creation that the real script would do
    async def create_manifest(*args, **kwargs):
        # find the --output-dir argument from args
        # NOTE: the side effect receives the positional arguments passed to subprocess_exec!
        # args contains self.blender_bin, "-b", ...
        output_dir = tmp_path
        render_id = "test_render"
        for i, arg in enumerate(args):
            if arg == "--output-dir":
                output_dir = args[i+1]
            if arg == "--render-id":
                render_id = args[i+1]

        manifest_data = {
            "render_id": render_id,
            "frame_count": 36,
            "avg_frame_time_ms": 100.0,
            "resolution": "640x360",
            "output_video_path": f"{output_dir}/{render_id}.mp4",
            "engine": "EEVEE"
        }

        import os
        with open(os.path.join(output_dir, f"{render_id}_manifest.json"), "w") as f:
            json.dump(manifest_data, f)

        return mock_process

    with mock.patch("asyncio.create_subprocess_exec", side_effect=create_manifest):
        # Path.exists needs to let it check the script exists, but we can let it actually check since it does exist
        manifest = await adapter.render_turntable("/mock/model.obj", str(tmp_path), "preview")

    assert isinstance(manifest, BlenderRenderManifest)
    assert manifest.frame_count == 36
    assert manifest.engine == "EEVEE"

@pytest.mark.asyncio
async def test_run_benchmark_success(mock_blender_binary):
    adapter = BlenderSceneAdapter()

    mock_process = AsyncMock()
    mock_process.returncode = 0
    benchmark_json = '{"540p": {"fps": 30.5}}'
    mock_process.communicate.return_value = (f"something\n---BENCHMARK_RESULT_START---{benchmark_json}---BENCHMARK_RESULT_END---\nelse".encode(), b"")

    with mock.patch("asyncio.create_subprocess_exec", return_value=mock_process):
        with mock.patch("pathlib.Path.exists", return_value=True):
            stats = await adapter.run_benchmark("/mock/model.obj")

    assert "540p" in stats
    assert stats["540p"]["fps"] == 30.5
