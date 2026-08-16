"""Create a no-API technical demo of the Shorts render pipeline."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.application.services.premium_subtitle_formatter import PremiumSubtitleFormatter
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.word_timing import WordTiming
from infrastructure.providers.render.ffmpeg_render_provider import FfmpegRenderProvider


OUTPUT_DIRECTORY = PROJECT_ROOT / "output" / "prototype_demo"


async def _run(*command: str) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace")[-2_000:])


async def main() -> Path:
    """Generate synthetic media, karaoke captions, and a vertical MP4 demo."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    audio_path = OUTPUT_DIRECTORY / "prototype.wav"
    background_path = OUTPUT_DIRECTORY / "prototype_background.mp4"
    subtitle_path = OUTPUT_DIRECTORY / "prototype.ass"
    output_path = OUTPUT_DIRECTORY / "shorts_factory_prototype.mp4"

    await _run(
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        "sine=frequency=220:sample_rate=48000:duration=12",
        "-af", "volume=0.18", str(audio_path),
    )
    await _run(
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=1080x1920:rate=30:duration=12",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(background_path),
    )

    words = [
        WordTiming("SHORTS", 500, 1_250),
        WordTiming("FACTORY", 1_250, 2_000),
        WordTiming("DEMO", 2_000, 2_750),
        WordTiming("IS", 2_750, 3_250),
        WordTiming("NOW", 4_000, 4_700),
        WordTiming("RUNNING", 4_700, 5_600),
        WordTiming("AUTONOMOUSLY", 5_600, 6_700),
    ]
    cues = [
        SubtitleCue.from_words(words[:4], index=1),
        SubtitleCue.from_words(words[4:], index=2),
    ]
    subtitle_path.write_text(PremiumSubtitleFormatter().format(cues), encoding="utf-8")

    renderer = FfmpegRenderProvider()
    await renderer.render_shorts(
        str(audio_path),
        str(subtitle_path),
        [str(background_path)],
        str(output_path),
        audio_start_ms=0,
        audio_end_ms=12_000,
    )
    return output_path


if __name__ == "__main__":
    rendered = asyncio.run(main())
    print(rendered)
