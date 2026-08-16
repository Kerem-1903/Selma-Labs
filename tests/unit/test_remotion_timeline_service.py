from __future__ import annotations

from core.application.services.remotion_timeline_service import RemotionTimelineService
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.visual_intent import VisualIntent
from core.domain.value_objects.word_timing import WordTiming


def test_builds_frame_accurate_motion_contract(tmp_path):
    clip = tmp_path / "octopus.mp4"
    clip.write_bytes(b"video")
    cue = SubtitleCue.from_words(
        [
            WordTiming("Bir", 0, 180, 0.99),
            WordTiming("ahtapotun", 180, 520, 0.99),
            WordTiming("üç", 520, 700, 0.99),
            WordTiming("kalbi", 700, 1_000, 0.99),
        ]
    )
    intent = VisualIntent(
        primary_keyword="octopus",
        mood="mysterious",
        motion_type="fast-paced",
        start_ms=0,
        end_ms=1_000,
        narrative_role="hook",
        shot_type="macro-close-up",
        visual_job="open_hook",
        overlay_labels=("3 KALP",),
    )

    timeline = RemotionTimelineService().build(
        title="Ahtapotların neden üç kalbi vardır?",
        cues=[cue],
        visual_intents=[intent],
        video_clips=[str(clip)],
    )

    assert timeline["durationInFrames"] == 30
    assert timeline["hookText"] == "ÜÇ KALBİ"
    assert timeline["brandSignature"] == "STRANGE THINGS"
    assert timeline["brandStartFrame"] == 1
    assert timeline["brandDurationFrames"] == 29
    assert timeline["ctaText"] == "DAHA GARİBİ İÇİN TAKİP ET"
    assert timeline["scenes"][0]["transition"] == "hard"
    assert timeline["scenes"][0]["source"] == clip.resolve().as_uri()
    assert timeline["captions"][0]["words"][2] == {
        "text": "üç",
        "startFrame": 16,
        "endFrame": 21,
    }


def test_assigns_semantic_transitions():
    service = RemotionTimelineService()
    intent = VisualIntent(
        primary_keyword="heart",
        mood="clear",
        motion_type="steady",
        start_ms=1_000,
        end_ms=2_000,
        visual_job="demonstrate_mechanism",
    )

    assert service._transition_for(intent, 1) == "match_zoom"


def test_uses_product_specific_cta_for_material_topics(tmp_path):
    clip = tmp_path / "polymer.mp4"
    clip.write_bytes(b"video")
    cue = SubtitleCue.from_words(
        [WordTiming("This", 0, 200), WordTiming("heals.", 200, 600)]
    )
    intent = VisualIntent(
        primary_keyword="polymer",
        mood="clear",
        motion_type="steady",
        start_ms=0,
        end_ms=600,
    )

    timeline = RemotionTimelineService().build(
        title="Self-healing materials",
        cues=[cue],
        visual_intents=[intent],
        video_clips=[str(clip)],
    )

    assert timeline["ctaText"] == "WHERE SHOULD WE USE THIS FIRST?"


def test_synchronizes_brand_sting_with_spoken_signature(tmp_path):
    clip = tmp_path / "brand.mp4"
    clip.write_bytes(b"video")
    cues = [
        SubtitleCue.from_words(
            [WordTiming("Strong", 0, 400), WordTiming("hook.", 400, 900)]
        ),
        SubtitleCue.from_words(
            [
                WordTiming("Welcome", 1_200, 1_500),
                WordTiming("to", 1_500, 1_650),
                WordTiming("Strange", 1_650, 1_950),
                WordTiming("Things.", 1_950, 2_300),
            ]
        ),
    ]
    intent = VisualIntent(
        primary_keyword="technology",
        mood="mysterious",
        motion_type="steady",
        start_ms=0,
        end_ms=2_300,
    )

    timeline = RemotionTimelineService().build(
        title="Future technology",
        cues=cues,
        visual_intents=[intent],
        video_clips=[str(clip)],
    )

    assert timeline["brandStartFrame"] == 36
    assert timeline["brandDurationFrames"] == 33


def test_uses_turkish_cta_for_turkish_material_topic(tmp_path):
    clip = tmp_path / "malzeme.mp4"
    clip.write_bytes(b"video")
    cue = SubtitleCue.from_words(
        [WordTiming("Kendini", 0, 300), WordTiming("onarıyor.", 300, 700)]
    )
    intent = VisualIntent(
        primary_keyword="kendini onaran polimer",
        mood="clear",
        motion_type="steady",
        start_ms=0,
        end_ms=700,
        overlay_labels=("ÇATLAK", "YENİDEN BAĞ"),
        explanation_mode="hybrid",
        explanatory_required=True,
    )

    timeline = RemotionTimelineService().build(
        title="Kendini Onaran Malzemeler",
        cues=[cue],
        visual_intents=[intent],
        video_clips=[str(clip)],
    )

    assert timeline["ctaText"] == "DAHA GARİBİ İÇİN TAKİP ET"
    assert timeline["scenes"][0]["diagramKind"] == "self_healing"


def test_uses_turkish_cta_when_localized_title_stays_english(tmp_path):
    clip = tmp_path / "airplane.mp4"
    clip.write_bytes(b"video")
    cue = SubtitleCue.from_words(
        [WordTiming("Uçak", 0, 250), WordTiming("penceresi", 250, 600)]
    )
    intent = VisualIntent(
        primary_keyword="airplane",
        mood="clear",
        motion_type="steady",
        start_ms=0,
        end_ms=600,
    )

    timeline = RemotionTimelineService().build(
        title="airplane",
        cues=[cue],
        visual_intents=[intent],
        video_clips=[str(clip)],
    )

    assert timeline["ctaText"] == "DAHA GARİBİ İÇİN TAKİP ET"
