from __future__ import annotations

from core.application.services.episode_director_service import EpisodeDirectorService
from core.application.services.trailer_director_service import TrailerDirectorService
from core.domain.value_objects.trailer_brief import TrailerBrief


def test_trailer_director_covers_exact_budget_with_traceable_shots():
    episode = EpisodeDirectorService().plan_text(
        "SCENE: Rooftop\nAKIRA: We move now.\nThe signal flickers.\n\nSCENE: Station\nAKIRA: The truth is here.",
        episode_id="episode-001",
    )
    plan = TrailerDirectorService().plan(episode, TrailerBrief(trailer_id="esik80-trailer-v1"))
    assert len(plan.shots) == 54
    assert plan.timeline.duration_frames == 4320
    assert plan.shots[0].start_frame == 0
    assert plan.shots[-1].end_frame == 4320
    assert all(shot.source_scene_id and shot.source_shot_id for shot in plan.shots)
    assert all(shot.spoiler_level != "HIDDEN" for shot in plan.shots)
    assert [shot.start_frame for shot in plan.shots] == sorted(shot.start_frame for shot in plan.shots)


def test_trailer_director_sets_mnemos_and_hybrid_music_cues():
    episode = EpisodeDirectorService().plan_text("SCENE: Rooftop\nAKIRA: We wait.")
    plan = TrailerDirectorService().plan(episode, TrailerBrief(trailer_id="trailer"))
    assert any(shot.system_voice == "MNEMOS" for shot in plan.shots)
    assert plan.shots[0].music_cue == "rain-and-three-note-motif"
    assert plan.shots[-1].music_cue == "music-cut-then-title-strike"
