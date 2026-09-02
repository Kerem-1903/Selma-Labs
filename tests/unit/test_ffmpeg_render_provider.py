"""
Unit tests for FfmpegRenderProvider.

Unlike PexelsProvider/ElevenLabsVoiceProvider (network-backed, mocked at
the httpx layer), FfmpegRenderProvider's external dependency is a *local*
subprocess, not a network call -- same category as LocalFsStorage's real
filesystem I/O, which that adapter's own test file already exercises for
real rather than mocking. Consistent with that precedent, these tests
invoke the real ``ffmpeg``/``ffprobe`` binaries against tiny synthetic
fixtures generated with FFmpeg's own ``lavfi`` test-source input (a solid
color video, a sine-wave tone) -- no real video/audio files, no network, no
API key, and no meaningful runtime cost. Skipped automatically in any
environment where FFmpeg isn't installed, since (unlike this project's
network-backed providers) there is no way to fake a local binary's absence
the way an API key can be faked.
"""
from __future__ import annotations

import asyncio
import shutil

import pytest

from core.application.services.premium_subtitle_formatter import PremiumSubtitleFormatter
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.timeline import Timeline
from core.domain.exceptions import RenderError, RenderExecutionError
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.timeline_clip import TimelineClip
from core.domain.value_objects.visual_intent import VisualIntent
from core.domain.value_objects.word_timing import WordTiming
from infrastructure.providers.render.ffmpeg_render_provider import FfmpegRenderProvider


def test_mp3_boundary_rounding_is_clamped_within_one_frame_tolerance():
    assert FfmpegRenderProvider._normalize_audio_end_ms(26_645, 26_610) == 26_610


def test_audio_boundary_still_rejects_material_overshoot():
    with pytest.raises(RenderExecutionError, match="exceed"):
        FfmpegRenderProvider._normalize_audio_end_ms(26_700, 26_610)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

pytestmark = pytest.mark.skipif(
    not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe not installed on PATH"
)


async def _make_fixture_clip(path, duration: float, color: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.communicate()
    assert process.returncode == 0


async def _make_fixture_audio(path, duration: float) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:a", "aac",
        str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.communicate()
    assert process.returncode == 0


def _scene(index: int, start_time: float, end_time: float) -> Scene:
    return Scene(
        index=index,
        narration="narration",
        search_keywords=["kw"],
        detected_objects=[],
        location="",
        mood="",
        visual_priority="high",
        start_time=start_time,
        end_time=end_time,
    )


def _asset(local_path: str) -> MediaAsset:
    return MediaAsset(
        id="pexels:1",
        provider="pexels",
        provider_asset_id="1",
        media_type="video",
        original_url="https://videos.pexels.com/1.mp4",
        thumbnail_url="https://images.pexels.com/thumb.jpeg",
        width=320,
        height=240,
        duration_seconds=2.0,
        fps=25.0,
        tags=[],
        attribution="Test",
        license="Test License",
        local_path=local_path,
    )


@pytest.mark.asyncio
async def test_render_produces_a_playable_file_with_expected_properties(tmp_path):
    clip_a = tmp_path / "clip_a.mp4"
    clip_b = tmp_path / "clip_b.mp4"
    audio = tmp_path / "narration.aac"
    await _make_fixture_clip(clip_a, duration=1.0, color="red")
    await _make_fixture_clip(clip_b, duration=1.0, color="blue")
    await _make_fixture_audio(audio, duration=2.0)

    clips = [
        TimelineClip(scene=_scene(0, 0.0, 1.0), asset=_asset(str(clip_a))),
        TimelineClip(scene=_scene(1, 1.0, 2.0), asset=_asset(str(clip_b))),
    ]
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=clips)

    provider = FfmpegRenderProvider(output_width=160, output_height=120, fps=24)
    result = await provider.render(timeline, str(audio))

    try:
        assert result.width == 160
        assert result.height == 120
        # Total duration should be close to the sum of both clips (~2s),
        # within encoding/rounding tolerance.
        assert 1.5 <= result.duration_seconds <= 2.5
        import os

        assert os.path.exists(result.output_path)
        assert os.path.getsize(result.output_path) > 0
    finally:
        import os

        if os.path.exists(result.output_path):
            os.remove(result.output_path)


@pytest.mark.asyncio
async def test_render_burns_subtitles_into_video(tmp_path):
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "narration.aac"
    subtitles = tmp_path / "captions.srt"
    await _make_fixture_clip(clip, duration=1.0, color="black")
    await _make_fixture_audio(audio, duration=1.0)
    subtitles.write_text(
        "1\n00:00:00,000 --> 00:00:00,900\nSELMA TEST\n",
        encoding="utf-8",
    )
    timeline = Timeline.create(
        asset_match_plan_id="plan-1",
        clips=[TimelineClip(scene=_scene(0, 0.0, 1.0), asset=_asset(str(clip)))],
    )

    provider = FfmpegRenderProvider(output_width=160, output_height=120, fps=24)
    result = await provider.render(timeline, str(audio), str(subtitles))

    try:
        assert result.width == 160
        assert result.height == 120
        assert result.duration_seconds > 0
    finally:
        import os

        if os.path.exists(result.output_path):
            os.remove(result.output_path)


@pytest.mark.asyncio
async def test_rejects_missing_subtitle_file(tmp_path):
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "narration.aac"
    await _make_fixture_clip(clip, duration=1.0, color="green")
    await _make_fixture_audio(audio, duration=1.0)
    timeline = Timeline.create(
        asset_match_plan_id="plan-1",
        clips=[TimelineClip(scene=_scene(0, 0.0, 1.0), asset=_asset(str(clip)))],
    )

    provider = FfmpegRenderProvider()

    with pytest.raises(RenderError, match="Subtitle file not found"):
        await provider.render(
            timeline, str(audio), str(tmp_path / "missing-captions.srt")
        )


@pytest.mark.asyncio
async def test_raises_render_error_for_empty_timeline():
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=[])
    provider = FfmpegRenderProvider()

    with pytest.raises(RenderError, match="no clips"):
        await provider.render(timeline, "/nonexistent/narration.mp3")


@pytest.mark.asyncio
async def test_raises_render_error_for_missing_narration_audio(tmp_path):
    clip = tmp_path / "clip.mp4"
    await _make_fixture_clip(clip, duration=1.0, color="green")
    clips = [TimelineClip(scene=_scene(0, 0.0, 1.0), asset=_asset(str(clip)))]
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=clips)
    provider = FfmpegRenderProvider()

    with pytest.raises(RenderError, match="Narration audio file not found"):
        await provider.render(timeline, str(tmp_path / "does-not-exist.mp3"))


@pytest.mark.asyncio
async def test_raises_render_error_on_missing_ffmpeg_binary(tmp_path):
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "narration.aac"
    await _make_fixture_clip(clip, duration=1.0, color="green")
    await _make_fixture_audio(audio, duration=1.0)
    clips = [TimelineClip(scene=_scene(0, 0.0, 1.0), asset=_asset(str(clip)))]
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=clips)

    provider = FfmpegRenderProvider(ffmpeg_binary="ffmpeg-does-not-exist")

    with pytest.raises(RenderError, match="Could not find binary"):
        await provider.render(timeline, str(audio))


@pytest.mark.asyncio
async def test_raises_render_error_for_non_positive_scene_duration(tmp_path):
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "narration.aac"
    await _make_fixture_clip(clip, duration=1.0, color="green")
    await _make_fixture_audio(audio, duration=1.0)
    # end_time == start_time -> zero duration, must be rejected before
    # ever invoking ffmpeg on a degenerate trim.
    clips = [TimelineClip(scene=_scene(0, 1.0, 1.0), asset=_asset(str(clip)))]
    timeline = Timeline.create(asset_match_plan_id="plan-1", clips=clips)
    provider = FfmpegRenderProvider()

    with pytest.raises(RenderError, match="non-positive duration"):
        await provider.render(timeline, str(audio))


@pytest.mark.asyncio
async def test_render_shorts_loops_clips_and_burns_ass_subtitles(tmp_path):
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "song.aac"
    subtitles = tmp_path / "captions.ass"
    output = tmp_path / "short.mp4"
    await _make_fixture_clip(clip, duration=0.5, color="purple")
    await _make_fixture_audio(audio, duration=2.0)
    subtitles.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,"
        "ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,"
        "MarginR,MarginV,Encoding\n"
        "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,SELMA\n",
        encoding="utf-8",
    )
    provider = FfmpegRenderProvider(output_width=160, output_height=120, fps=24)

    rendered = await provider.render_shorts(
        str(audio),
        str(subtitles),
        [str(clip)],
        str(output),
        audio_start_ms=500,
        audio_end_ms=1_500,
    )

    assert rendered == str(output.resolve())
    assert output.exists()
    assert output.stat().st_size > 0


def test_shorts_segment_plan_enforces_maximum_cut_duration():
    provider = FfmpegRenderProvider(maximum_cut_duration_seconds=3.5)

    segments = provider._plan_shorts_segments(
        ["first.mp4", "second.mp4"],
        target_duration_seconds=8.0,
    )

    assert len(segments) == 3
    assert [duration for _, duration, _ in segments] == [3.5, 3.5, 1.0]
    assert [path.name for path, _, _ in segments] == [
        "first.mp4",
        "second.mp4",
        "first.mp4",
    ]


def test_shorts_segment_plan_preserves_storyboard_cut_durations():
    provider = FfmpegRenderProvider(maximum_cut_duration_seconds=3.5)

    segments = provider._plan_shorts_segments(
        ["hook.mp4", "context.mp4", "payoff.mp4"],
        target_duration_seconds=6.0,
        clip_durations_seconds=[1.5, 2.4, 2.1],
    )

    assert [duration for _, duration, _ in segments] == [1.5, 2.4, 2.1]
    assert [path.name for path, _, _ in segments] == [
        "hook.mp4",
        "context.mp4",
        "payoff.mp4",
    ]


def test_shorts_segment_plan_rejects_storyboard_timeline_gap():
    provider = FfmpegRenderProvider(maximum_cut_duration_seconds=3.5)

    with pytest.raises(RenderExecutionError, match="cover the selected audio"):
        provider._plan_shorts_segments(
            ["hook.mp4", "payoff.mp4"],
            target_duration_seconds=6.0,
            clip_durations_seconds=[1.5, 2.0],
        )


def test_shot_grammar_creates_materially_different_crops_for_reused_footage():
    provider = FfmpegRenderProvider(output_width=1080, output_height=1920)

    wide = provider._motion_filter(0.0, "steady", "wide-establishing")
    detail = provider._motion_filter(0.0, "steady", "detail-insert")

    assert "scale=1112:1977" in wide
    assert "scale=1317:2342" in detail
    assert wide != detail


def test_visual_job_changes_camera_motion_without_adding_a_transition():
    provider = FfmpegRenderProvider(output_width=1080, output_height=1920)

    mechanism = provider._motion_filter(
        0.0,
        "steady",
        "tracking-medium",
        "demonstrate_mechanism",
    )
    payoff = provider._motion_filter(
        0.0,
        "steady",
        "tracking-medium",
        "deliver_payoff",
    )

    assert "29*sin" in mechanism
    assert "9*sin" in payoff
    assert "fade=" not in mechanism
    assert mechanism != payoff


@pytest.mark.asyncio
async def test_shorts_single_pass_command_enforces_premium_output_profile(monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "narration.mp3"
    subtitles = tmp_path / "captions.ass"
    output = tmp_path / "short.mp4"
    clip.touch()
    audio.touch()
    subtitles.write_text("[Script Info]\n", encoding="utf-8")
    commands: list[list[str]] = []

    async def fake_run(command, *, context, capture=False):
        del context, capture
        if command[0] == "ffprobe":
            return "2.0\n"
        commands.append(command)
        output.write_bytes(b"mp4")
        return ""

    provider = FfmpegRenderProvider(output_width=160, output_height=120, fps=24)
    monkeypatch.setattr(provider, "_run", fake_run)

    await provider.render_shorts(
        str(audio),
        str(subtitles),
        [str(clip)],
        str(output),
        audio_start_ms=0,
        audio_end_ms=2_000,
    )

    assert len(commands) == 1
    command = commands[0]
    filter_graph = command[command.index("-filter_complex") + 1]
    assert "concat=n=1:v=1:a=0" in filter_graph
    assert "loudnorm=I=-14.0:TP=-1.5:LRA=9" in filter_graph
    assert "alimiter=limit=0.95" in filter_graph
    assert "fade=t=in" not in filter_graph
    assert command[command.index("-crf") + 1] == "17"
    assert command[command.index("-profile:v") + 1] == "high"
    assert command[command.index("-colorspace") + 1] == "bt709"
    assert command[command.index("-movflags") + 1] == "+faststart"


@pytest.mark.asyncio
async def test_shorts_single_pass_ducks_licensed_music_under_narration(monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    narration = tmp_path / "narration.mp3"
    music = tmp_path / "licensed-music.mp3"
    subtitles = tmp_path / "captions.ass"
    output = tmp_path / "short.mp4"
    for path in (clip, narration, music):
        path.touch()
    subtitles.write_text("[Script Info]\n", encoding="utf-8")
    commands: list[list[str]] = []

    async def fake_run(command, *, context, capture=False):
        del context, capture
        if command[0] == "ffprobe":
            return "3.0\n"
        commands.append(command)
        output.write_bytes(b"mp4")
        return ""

    provider = FfmpegRenderProvider(
        output_width=160,
        output_height=120,
        fps=24,
        background_music_volume=0.14,
    )
    monkeypatch.setattr(provider, "_run", fake_run)

    await provider.render_shorts(
        str(narration),
        str(subtitles),
        [str(clip)],
        str(output),
        audio_end_ms=3_000,
        background_music_path=str(music),
        procedural_audio_accents=True,
    )

    command = commands[0]
    filter_graph = command[command.index("-filter_complex") + 1]
    assert "highpass=f=70" in filter_graph
    assert "acompressor=threshold=0.125:ratio=3" in filter_graph
    assert "volume='0.140000':eval=frame" in filter_graph
    assert "sidechaincompress=threshold=0.025:ratio=10" in filter_graph
    assert "amix=inputs=2:duration=first" in filter_graph
    assert "aevalsrc='(sin(2*PI*62*t)" in filter_graph
    assert "amix=inputs=3:duration=first:dropout_transition=0:normalize=0" in filter_graph
    assert command.count("-stream_loop") == 2


@pytest.mark.asyncio
async def test_shorts_renders_real_narration_and_music_ducking_graph(tmp_path):
    clip = tmp_path / "clip.mp4"
    narration = tmp_path / "narration.aac"
    music = tmp_path / "music.aac"
    subtitles = tmp_path / "captions.ass"
    output = tmp_path / "mixed-short.mp4"
    await _make_fixture_clip(clip, duration=2.2, color="navy")
    await _make_fixture_audio(narration, duration=2.2)
    await _make_fixture_audio(music, duration=2.2)
    subtitles.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,"
        "ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,"
        "MarginR,MarginV,Encoding\n"
        "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n",
        encoding="utf-8",
    )
    provider = FfmpegRenderProvider(output_width=160, output_height=120, fps=24)

    rendered = await provider.render_shorts(
        str(narration),
        str(subtitles),
        [str(clip)],
        str(output),
        audio_end_ms=2_000,
        background_music_path=str(music),
        procedural_audio_accents=True,
    )

    assert rendered == str(output.resolve())
    assert output.exists()
    assert output.stat().st_size > 0


@pytest.mark.asyncio
async def test_shorts_renders_complete_studio_sound_plan_with_ambience_and_automation(tmp_path):
    from core.application.services.sound_design_planning_service import SoundDesignPlanningService
    from core.domain.value_objects.visual_intent import VisualIntent

    clip = tmp_path / "clip.mp4"
    narration = tmp_path / "narration.aac"
    music = tmp_path / "music.aac"
    subtitles = tmp_path / "captions.ass"
    output = tmp_path / "studio-short.mp4"
    await _make_fixture_clip(clip, duration=2.2, color="navy")
    await _make_fixture_audio(narration, duration=2.2)
    await _make_fixture_audio(music, duration=2.2)
    subtitles.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
        "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,"
        "ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,"
        "MarginR,MarginV,Encoding\n"
        "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n",
        encoding="utf-8",
    )
    intents = [
        VisualIntent("space", "mystery", "steady", start_ms=0, end_ms=1_000, narrative_role="hook", visual_job="establish_question"),
        VisualIntent("planet", "mystery", "steady", start_ms=1_000, end_ms=2_000, narrative_role="payoff", visual_job="deliver_payoff"),
    ]
    plan = SoundDesignPlanningService().plan(intents, has_music=True)
    provider = FfmpegRenderProvider(output_width=160, output_height=120, fps=24)

    rendered = await provider.render_shorts(
        str(narration), str(subtitles), [str(clip)], str(output),
        audio_end_ms=2_000, background_music_path=str(music),
        sound_design_plan=plan.to_dict(),
    )

    assert rendered == str(output.resolve())
    assert output.stat().st_size > 0


@pytest.mark.asyncio
async def test_real_ffmpeg_accepts_animated_caption_and_semantic_overlay(tmp_path):
    clip = tmp_path / "clip.mp4"
    narration = tmp_path / "narration.aac"
    subtitles = tmp_path / "animated.ass"
    output = tmp_path / "animated-short.mp4"
    await _make_fixture_clip(clip, duration=1.7, color="navy")
    await _make_fixture_audio(narration, duration=1.7)
    cue = SubtitleCue.from_words(
        [WordTiming("Kan", 0, 350), WordTiming("pompalar", 360, 900)]
    )
    intent = VisualIntent(
        "octopus",
        "reflective",
        "steady",
        start_ms=0,
        end_ms=1_500,
        visual_job="demonstrate_mechanism",
        shot_type="detail-insert",
        explanation_mode="hybrid",
        overlay_labels=("KALP → SOLUNGAÇ",),
        explanatory_required=True,
    )
    subtitles.write_text(
        PremiumSubtitleFormatter().format([cue], [intent]),
        encoding="utf-8",
    )
    provider = FfmpegRenderProvider(output_width=160, output_height=284, fps=24)

    rendered = await provider.render_shorts(
        str(narration),
        str(subtitles),
        [str(clip)],
        str(output),
        audio_end_ms=1_500,
        clip_durations_seconds=[1.5],
        motion_types=["steady"],
        shot_types=["detail-insert"],
        visual_jobs=["demonstrate_mechanism"],
    )

    assert rendered == str(output.resolve())
    assert output.stat().st_size > 0


@pytest.mark.asyncio
async def test_run_timeout_terminates_and_reaps_ffmpeg(monkeypatch):
    class HangingProcess:
        def __init__(self) -> None:
            self.returncode: int | None = None
            self.terminated = False
            self._finished = asyncio.Event()

        async def communicate(self) -> tuple[bytes, bytes]:
            await self._finished.wait()
            return b"", b""

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.returncode = -9
            self._finished.set()

        async def wait(self) -> int:
            self.returncode = -15
            self._finished.set()
            return self.returncode

    process = HangingProcess()

    async def create_hanging_process(*args, **kwargs):
        return process

    monkeypatch.setattr(
        "infrastructure.providers.render.ffmpeg_render_provider.asyncio.create_subprocess_exec",
        create_hanging_process,
    )
    provider = FfmpegRenderProvider(subprocess_timeout_seconds=0.01)

    with pytest.raises(RenderExecutionError, match="Timed out"):
        await provider._run(["ffmpeg"], context="test timeout")

    assert process.terminated is True
    assert process.returncode == -15
