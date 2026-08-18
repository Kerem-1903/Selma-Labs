import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.domain.exceptions import RenderError
from infrastructure.providers.render.nvenc_fast_render_adapter import NVENCFastRenderAdapter


@pytest.fixture
def adapter():
    return NVENCFastRenderAdapter(use_gpu=True, ffmpeg_path="ffmpeg")


@pytest.mark.asyncio
async def test_raises_error_if_no_video_clips(adapter):
    with pytest.raises(RenderError, match="No video clips provided"):
        await adapter.render_shorts(
            audio_path="voice.mp3",
            subtitle_ass_path="subs.ass",
            video_clips=[],
            output_path="out.mp4"
        )


@pytest.mark.asyncio
async def test_builds_and_executes_ffmpeg_command(adapter, tmp_path):
    output_path = tmp_path / "out.mp4"
    audio_path = tmp_path / "voice.mp3"
    bgm_path = tmp_path / "bgm.mp3"
    video_clips = [str(tmp_path / "1.mp4"), str(tmp_path / "2.mp4")]

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.pid = 12345
    async def mock_communicate():
        return (b"stdout", b"stderr")
    mock_process.communicate = mock_communicate

    with patch("asyncio.create_subprocess_exec") as mock_exec, \
         patch("os.setsid"), patch("os.killpg"), patch("os.getpgid"), \
         patch("infrastructure.providers.render.smart_cropping_service.SmartCroppingService.get_crop_filter", return_value="crop=1080:1920:0:0"):

        async def mock_create(*args, **kwargs):
            return mock_process
        mock_exec.side_effect = mock_create

        result = await adapter.render_shorts(
            audio_path=str(audio_path),
            subtitle_ass_path="subs.ass",
            video_clips=video_clips,
            output_path=str(output_path),
            background_music_path=str(bgm_path)
        )

        assert result == str(output_path)
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]

        assert "ffmpeg" in args
        assert "-hwaccel" in args
        assert "cuda" in args
        assert "h264_nvenc" in args
        assert "-filter_complex" in args

        # Check audio ducking logic exists
        filter_str = args[args.index("-filter_complex") + 1]
        assert "sidechaincompress" in filter_str
        assert "concat=n=2:v=1:a=0" in filter_str
        assert "crop=1080:1920:0:0" in filter_str

@pytest.mark.asyncio
async def test_handles_ffmpeg_failure(adapter, tmp_path):
    output_path = tmp_path / "out.mp4"
    video_clips = [str(tmp_path / "1.mp4")]

    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.pid = 12345
    # Python 3.8+ asyncio.coroutine is gone, use an async def
    async def mock_communicate():
        return b"", b"Fatal error in ffmpeg"
    mock_process.communicate = mock_communicate

    with patch("asyncio.create_subprocess_exec") as mock_exec, \
         patch("os.setsid"), patch("os.killpg"), patch("os.getpgid"):

        async def mock_create(*args, **kwargs):
            return mock_process
        mock_exec.side_effect = mock_create

        with pytest.raises(RenderError, match="NVENC rendering failed: Fatal error in ffmpeg"):
            await adapter.render_shorts(
                audio_path="voice.mp3",
                subtitle_ass_path="subs.ass",
                video_clips=video_clips,
                output_path=str(output_path)
            )
