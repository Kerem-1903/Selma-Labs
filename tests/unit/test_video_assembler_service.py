import pytest
import os
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
from core.application.services.video_assembler_service import VideoAssemblerService
from core.domain.entities.media_asset import MediaAsset

@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    storage.download_file = MagicMock(return_value=True)
    return storage

@pytest.mark.asyncio
async def test_assemble_sequence_success(mock_storage):
    service = VideoAssemblerService(storage=mock_storage)

    shots = [
        MediaAsset(id="1", provider="mock", original_url="mock://vid1.mp4", duration_seconds=2.0),
        MediaAsset(id="2", provider="mock", original_url="mock://vid2.mp4", duration_seconds=3.0)
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        out_path = os.path.join(temp_dir, "output.mp4")

        # Mock FFmpeg execution
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b"stdout", b"stderr")

        with patch('asyncio.create_subprocess_exec', return_value=mock_process) as mock_exec:
            res = await service.assemble_sequence(shots, out_path)

            assert res == out_path
            mock_exec.assert_called_once()
            args, _ = mock_exec.call_args
            assert args[0] == "ffmpeg"
            assert "-f" in args
            assert "concat" in args

@pytest.mark.asyncio
async def test_assemble_sequence_empty():
    service = VideoAssemblerService(storage=AsyncMock())
    with pytest.raises(ValueError, match="No shots provided for assembly"):
        await service.assemble_sequence([], "out.mp4")
