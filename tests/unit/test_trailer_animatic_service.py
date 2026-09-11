from __future__ import annotations

import asyncio

from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.trailer_animatic_service import TrailerAnimaticService
from core.application.services.trailer_director_service import TrailerDirectorService
from core.domain.value_objects.trailer_audio_cue import TrailerAudioCue
from core.domain.value_objects.trailer_brief import TrailerBrief
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _trailer():
    episode = EpisodeDirectorService().plan_text(
        "SCENE: Rooftop\nAKIRA: We move now.\n\nSCENE: Station\nMNEMOS: The signal is close.\nAKIRA: Run!",
        episode_id="episode-001",
    )
    return TrailerDirectorService().plan(episode, TrailerBrief(trailer_id="trailer-smoke"))


def test_trailer_strict_requires_assets_without_building_project(tmp_path):
    plan = _trailer()
    selected = [plan.shots[0].shot_id, plan.shots[1].shot_id, plan.shots[2].shot_id]
    project = asyncio.run(
        TrailerAnimaticService(LocalFsStorage(str(tmp_path))).build(
            plan, shot_ids=selected, mode="STRICT"
        )
    )
    assert project is None


def test_trailer_placeholder_preserves_selected_frame_durations(tmp_path):
    plan = _trailer()
    selected = [plan.shots[0].shot_id, plan.shots[1].shot_id, plan.shots[2].shot_id]
    project = asyncio.run(
        TrailerAnimaticService(LocalFsStorage(str(tmp_path))).build(
            plan, shot_ids=selected, mode="PLACEHOLDER"
        )
    )
    assert project is not None
    assert project.production_plan_id == "trailer-smoke"
    assert project.project_kind == "TRAILER"
    assert project.duration_in_frames == sum(plan.shots[index].duration_frames for index in range(3))
    assert all(clip.image_storage_key.startswith("placeholder://") for clip in project.clips)


def test_trailer_audio_cues_are_carried_to_remotion_contract(tmp_path):
    plan = _trailer()
    cue = TrailerAudioCue(
        cue_id="music-01", kind="MUSIC", storage_key="audio/music.wav",
        start_frame=0, end_frame=48, gain_db=-12, fade_in_frames=8,
        fade_out_frames=8, ducking_db=-6,
    )
    project = asyncio.run(
        TrailerAnimaticService(LocalFsStorage(str(tmp_path))).build(
            plan, shot_ids=[plan.shots[0].shot_id], audio_cues=[cue], mode="PLACEHOLDER"
        )
    )
    assert project is not None
    assert project.audio_cues[0]["start_frame"] == 0
    assert project.audio_cues[0]["ducking_db"] == -6


def test_selected_trailer_shot_remaps_audio_timeline_and_source_offset(tmp_path):
    plan = _trailer()
    selected = plan.shots[1]
    cue = TrailerAudioCue(
        cue_id="music-late",
        kind="MUSIC",
        storage_key="audio/music.wav",
        start_frame=0,
        end_frame=selected.end_frame,
        fade_in_frames=8,
        fade_out_frames=8,
    )

    project = asyncio.run(
        TrailerAnimaticService(LocalFsStorage(str(tmp_path))).build(
            plan,
            shot_ids=[selected.shot_id],
            audio_cues=[cue],
            mode="PLACEHOLDER",
        )
    )

    assert project is not None
    assert project.audio_cues == (
        {
            **cue.to_dict(),
            "start_frame": 0,
            "end_frame": selected.duration_frames,
            "duration_frames": selected.duration_frames,
            "trim_before_frames": selected.start_frame,
            "source_duration_frames": cue.duration_frames,
        },
    )


def test_non_adjacent_selected_shots_split_one_audio_cue(tmp_path):
    plan = _trailer()
    first, third = plan.shots[0], plan.shots[2]
    cue = TrailerAudioCue(
        cue_id="music-bed",
        kind="MUSIC",
        storage_key="audio/music.wav",
        start_frame=first.start_frame,
        end_frame=third.end_frame,
    )

    project = asyncio.run(
        TrailerAnimaticService(LocalFsStorage(str(tmp_path))).build(
            plan,
            shot_ids=[first.shot_id, third.shot_id],
            audio_cues=[cue],
            mode="PLACEHOLDER",
        )
    )

    assert project is not None
    assert [item["cue_id"] for item in project.audio_cues] == [
        "music-bed:segment-01",
        "music-bed:segment-02",
    ]
    assert project.audio_cues[1]["start_frame"] == first.duration_frames
    assert project.audio_cues[1]["trim_before_frames"] == third.start_frame


def test_trailer_mnemos_shot_requires_audio_even_without_dialogue(tmp_path):
    plan = _trailer()
    mnemos = next(shot for shot in plan.shots if shot.system_voice == "MNEMOS")
    project = asyncio.run(
        TrailerAnimaticService(LocalFsStorage(str(tmp_path))).build(
            plan, shot_ids=[mnemos.shot_id], mode="STRICT"
        )
    )
    assert project is None
