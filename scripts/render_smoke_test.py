"""Create, render, inspect, and quality-check a real MP4 without network calls."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.application.services.post_render_quality_service import (  # noqa: E402
    PostRenderQualityService,
)
from core.application.services.premium_subtitle_formatter import (  # noqa: E402
    PremiumSubtitleFormatter,
)
from core.domain.value_objects.subtitle_cue import SubtitleCue  # noqa: E402
from core.domain.value_objects.word_timing import WordTiming  # noqa: E402
from infrastructure.providers.render.ffmpeg_media_quality_analysis_provider import (  # noqa: E402
    FfmpegMediaQualityAnalysisProvider,
)
from infrastructure.providers.render.ffmpeg_render_provider import (  # noqa: E402
    FfmpegRenderProvider,
)
from infrastructure.providers.render.ffprobe_media_inspection_provider import (  # noqa: E402
    FfprobeMediaInspectionProvider,
)


async def _run(command: list[str]) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        detail = (stderr or b"").decode("utf-8", errors="replace")[-2_000:]
        raise RuntimeError(f"Smoke fixture command failed: {detail}")


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="selma-real-render-") as temporary:
        root = Path(temporary)
        clip_a = root / "clip-a.mp4"
        clip_b = root / "clip-b.mp4"
        narration = root / "narration.wav"
        music = root / "music.wav"
        subtitles = root / "captions.ass"
        output = root / "smoke-output.mp4"

        await asyncio.gather(
            _run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc2=s=360x640:r=24:d=1.5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_a),
            ]),
            _run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "smptebars=s=360x640:r=24:d=1.5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip_b),
            ]),
            _run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
                "-c:a", "pcm_s16le", str(narration),
            ]),
            _run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=165:sample_rate=48000:duration=3",
                "-filter:a", "volume=0.18", "-c:a", "pcm_s16le", str(music),
            ]),
        )

        cues = [
            SubtitleCue.from_words([
                WordTiming("REAL", 0, 700),
                WordTiming("RENDER", 710, 1_450),
            ]),
            SubtitleCue.from_words([
                WordTiming("SMOKE", 1_500, 2_200),
                WordTiming("PASSED", 2_210, 2_950),
            ]),
        ]
        subtitles.write_text(
            PremiumSubtitleFormatter().format(cues), encoding="utf-8"
        )

        await FfmpegRenderProvider(
            output_width=360,
            output_height=640,
            fps=24,
        ).render_shorts(
            str(narration),
            str(subtitles),
            [str(clip_a), str(clip_b)],
            str(output),
            audio_start_ms=0,
            audio_end_ms=3_000,
            clip_durations_seconds=[1.5, 1.5],
            motion_types=["fast-paced", "steady"],
            shot_types=["macro-close-up", "wide-establishing"],
            visual_jobs=["establish_question", "deliver_payoff"],
            background_music_path=str(music),
            sound_design_plan={
                "schema_version": 1,
                "duration_ms": 3_000,
                "ambience_profile": "space",
                "cues": [
                    {
                        "timestamp_ms": 0,
                        "kind": "hook_impact",
                        "duration_ms": 320,
                        "gain_db": -20.0,
                        "rationale": "Exercise the opening sound-effect path.",
                    },
                    {
                        "timestamp_ms": 2_300,
                        "kind": "payoff",
                        "duration_ms": 420,
                        "gain_db": -22.0,
                        "rationale": "Exercise the payoff sound-effect path.",
                    },
                ],
                "music_automation": [
                    {
                        "timestamp_ms": 0,
                        "relative_gain_db": -4.0,
                        "purpose": "Keep the opening voice intelligible.",
                    },
                    {
                        "timestamp_ms": 2_000,
                        "relative_gain_db": 0.0,
                        "purpose": "Lift the music into the payoff.",
                    },
                ],
                "minimum_cue_gap_ms": 650,
                "target_integrated_lufs": -14.0,
                "target_true_peak_dbfs": -1.5,
            },
        )

        inspector = FfprobeMediaInspectionProvider()
        inspection = await inspector.inspect(str(output))
        signals = await FfmpegMediaQualityAnalysisProvider().analyze(str(output))
        quality = PostRenderQualityService()
        quality.validate(
            inspection,
            expected_duration_seconds=3.0,
            expected_width=360,
            expected_height=640,
        )
        quality.validate_content(signals, expected_duration_seconds=3.0)

        print(json.dumps({
            "status": "passed",
            "duration_seconds": inspection.duration_seconds,
            "dimensions": f"{inspection.width}x{inspection.height}",
            "video_codec": inspection.video_codec,
            "audio_codec": inspection.audio_codec,
            "integrated_lufs": signals.integrated_lufs,
            "true_peak_dbfs": signals.true_peak_dbfs,
            "scene_changes": len(signals.scene_change_timestamps_seconds),
            "bytes": output.stat().st_size,
        }))


if __name__ == "__main__":
    asyncio.run(main())
