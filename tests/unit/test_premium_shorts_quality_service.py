from core.application.services.premium_shorts_quality_service import (
    PremiumShortsQualityService,
)
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.scene_plan import ScenePlan
from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.entities.timeline import Timeline
from core.domain.entities.voice_track import VoiceTrack
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.timeline_clip import TimelineClip


def _scene(index: int) -> Scene:
    return Scene(
        index=index,
        narration="How can this happen?" if index == 0 else "short visual beat",
        search_keywords=["kangaroo"],
        detected_objects=["kangaroo"],
        location=None,
        mood=None,
        visual_priority="high",
        start_time=index * 3.0,
        end_time=(index + 1) * 3.0,
    )


def _asset(index: int) -> MediaAsset:
    return MediaAsset(
        id=f"asset-{index}",
        provider="fake",
        provider_asset_id=str(index),
        media_type="video",
        original_url="https://example.test/video.mp4",
        thumbnail_url="https://example.test/thumb.jpg",
        width=1080,
        height=1920,
        duration_seconds=5.0,
        fps=30.0,
        tags=["kangaroo"],
        attribution="Test",
        license="Test",
        local_path="C:/fake/video.mp4",
    )


def test_premium_quality_service_accepts_dense_varied_short():
    scenes = [_scene(index) for index in range(6)]
    scene_plan = ScenePlan.create(
        script_id="script",
        voice_track_id="voice",
        total_duration_seconds=18.0,
        provider_used="fake",
        scenes=scenes,
    )
    timeline = Timeline.create(
        asset_match_plan_id="matches",
        clips=[TimelineClip(scene=scene, asset=_asset(index)) for index, scene in enumerate(scenes)],
    )
    subtitles = SubtitleTrack.create(
        scene_plan_id=scene_plan.id,
        cues=[
            SubtitleCue(index=index + 1, scene_index=index, start_time=index * 2.0, end_time=(index + 1) * 2.0, text="short caption")
            for index in range(9)
        ],
    )
    voice = VoiceTrack.create(
        script_id="script",
        duration_seconds=18.0,
        provider="fake",
        voice_name="voice",
        sample_rate=48000,
        file_path="C:/fake/audio.mp3",
    )

    report = PremiumShortsQualityService().evaluate(
        voice_track=voice,
        scene_plan=scene_plan,
        timeline=timeline,
        subtitle_track=subtitles,
    )

    assert report.passed is True


def test_premium_quality_service_rejects_slow_single_scene():
    scene = _scene(0).finalize(index=0, start_time=0.0, end_time=18.0)
    scene_plan = ScenePlan.create(
        script_id="script",
        voice_track_id="voice",
        total_duration_seconds=18.0,
        provider_used="fake",
        scenes=[scene],
    )
    timeline = Timeline.create(
        asset_match_plan_id="matches",
        clips=[TimelineClip(scene=scene, asset=_asset(0))],
    )
    subtitles = SubtitleTrack.create(
        scene_plan_id=scene_plan.id,
        cues=[SubtitleCue(1, 0, 0.0, 18.0, "far too many words in one caption block")],
    )
    voice = VoiceTrack.create(
        script_id="script",
        duration_seconds=18.0,
        provider="fake",
        voice_name="voice",
        sample_rate=48000,
        file_path="C:/fake/audio.mp3",
    )

    report = PremiumShortsQualityService().evaluate(
        voice_track=voice,
        scene_plan=scene_plan,
        timeline=timeline,
        subtitle_track=subtitles,
    )

    assert report.passed is False
    assert "maximum_scene_duration" in {
        check.name for check in report.checks if not check.passed
    }
