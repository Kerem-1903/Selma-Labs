from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from core.application.services.asset_diversity_service import AssetDiversityService
from core.application.services.editorial_rhythm_service import EditorialRhythmService
from core.domain.entities.media_asset import MediaAsset
from core.domain.exceptions import AssetDiversityError, EditorialRhythmError
from core.domain.value_objects.asset_diversity import AssetUsage
from core.domain.value_objects.asset_score import AssetScore
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.visual_intent import VisualIntent
from core.domain.value_objects.word_timing import WordTiming


def _png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _pattern() -> Image.Image:
    image = Image.new("RGB", (100, 100))
    pixels = image.load()
    for y in range(100):
        for x in range(100):
            pixels[x, y] = ((x * 13 + y * 3) % 256, (x * 5) % 256, (y * 11) % 256)
    return image


def _candidate(
    asset_id: str,
    hashes: tuple[str, ...],
    *,
    pose: str = "",
    angle: str = "",
    background: str = "",
) -> ScoredAsset:
    return ScoredAsset(
        MediaAsset(
            id=asset_id,
            provider="fake",
            provider_asset_id=asset_id,
            metadata={
                "perceptual_hashes": list(hashes),
                "subject_pose": pose,
                "camera_angle": angle,
                "background_signature": background,
                "motion_energy": 0.6,
            },
        ),
        AssetScore(0.9),
    )


def _intent(
    *,
    start_ms: int = 0,
    end_ms: int = 1_400,
    visual_job: str = "establish_subject",
    shot_type: str = "macro-close-up",
    role: str = "hook",
    explanatory: bool = False,
) -> VisualIntent:
    return VisualIntent(
        "octopus",
        "reflective",
        "steady",
        start_ms=start_ms,
        end_ms=end_ms,
        visual_job=visual_job,
        shot_type=shot_type,
        narrative_role=role,
        explanation_mode="hybrid" if explanatory else "stock",
        overlay_labels=("3 HEARTS",) if explanatory else (),
        explanatory_required=explanatory,
    )


def test_crop_aware_hash_rejects_same_image_under_a_different_asset_id():
    service = AssetDiversityService()
    original = _pattern()
    cropped = original.crop((10, 10, 90, 90))
    original_hashes = service.fingerprint_frames([_png(original)])
    cropped_hashes = service.fingerprint_frames([_png(cropped)])
    first, first_usage = service.select(
        _intent(),
        [_candidate("asset-a", original_hashes)],
        [],
    )

    assert first.asset.id == "asset-a"
    with pytest.raises(AssetDiversityError, match="immediate perceptual repeat"):
        service.select(
            _intent(start_ms=1_400, end_ms=2_800),
            [_candidate("asset-b", cropped_hashes)],
            [first_usage],
        )


def test_motion_energy_uses_representative_frame_change():
    still = _png(_pattern())
    inverted = Image.eval(_pattern(), lambda value: 255 - value)

    static_energy = AssetDiversityService.motion_energy_from_frames(
        [still, still, still]
    )
    changing_energy = AssetDiversityService.motion_energy_from_frames(
        [still, _png(inverted), still]
    )

    assert static_energy == 0.0
    assert changing_energy > static_energy


def test_non_adjacent_source_reuse_requires_a_different_visual_function():
    service = AssetDiversityService()
    same_hash = ("0000000000000000",)
    _, first = service.select(
        _intent(),
        [_candidate("asset-a", same_hash, angle="macro")],
        [],
    )
    _, middle = service.select(
        _intent(start_ms=1_400, end_ms=2_800, shot_type="wide-establishing"),
        [_candidate("asset-b", ("ffffffffffffffff",), angle="wide")],
        [first],
    )

    selected, usage = service.select(
        _intent(
            start_ms=2_800,
            end_ms=4_200,
            visual_job="locate_part",
            shot_type="detail-insert",
            role="evidence",
            explanatory=True,
        ),
        [_candidate("asset-a", same_hash, angle="detail")],
        [first, middle],
    )

    assert selected.asset.id == "asset-a"
    assert usage.visual_job == "locate_part"


def test_subject_pose_budget_rejects_cosmetic_asset_variety():
    service = AssetDiversityService(maximum_pose_uses=2)
    history: list[AssetUsage] = []
    for index, value in enumerate(("0", "f")):
        _, usage = service.select(
            _intent(start_ms=index * 1_400, end_ms=(index + 1) * 1_400),
            [
                _candidate(
                    f"asset-{index}",
                    (value * 16,),
                    pose="octopus front-facing",
                    angle=f"angle-{index}",
                    background=f"background-{index}",
                )
            ],
            history,
        )
        history.append(usage)

    with pytest.raises(AssetDiversityError, match="subject-pose reuse budget"):
        service.select(
            _intent(start_ms=2_800, end_ms=4_200),
            [
                _candidate(
                    "asset-3",
                    ("aaaaaaaaaaaaaaaa",),
                    pose="octopus front-facing",
                    angle="angle-3",
                    background="background-3",
                )
            ],
            history,
        )


def _cue(start_ms: int, end_ms: int, first: str, second: str) -> SubtitleCue:
    midpoint = (start_ms + end_ms) // 2
    return SubtitleCue.from_words(
        [
            WordTiming(first, start_ms, midpoint - 10, 0.99),
            WordTiming(second, midpoint, end_ms, 0.99),
        ]
    )


def _usage(intent: VisualIntent, motion_energy: float) -> AssetUsage:
    return AssetUsage(
        asset_id=f"asset-{intent.start_ms}",
        perceptual_hashes=(),
        visual_job=intent.visual_job,
        shot_type=intent.shot_type,
        explanation_mode=intent.explanation_mode,
        overlay_labels=intent.overlay_labels,
        motion_energy=motion_energy,
        start_ms=intent.start_ms,
        end_ms=intent.end_ms,
    )


def test_rhythm_gate_rejects_long_unexplained_low_motion_hold():
    intents = [
        _intent(),
        _intent(
            start_ms=1_400,
            end_ms=4_400,
            visual_job="support_context",
            shot_type="wide-establishing",
            role="payoff",
        ),
    ]
    cues = [_cue(0, 1_400, "three", "hearts"), _cue(1_400, 4_400, "pump", "blood")]

    with pytest.raises(EditorialRhythmError, match=r"unresolved_low_motion=\[1\]"):
        EditorialRhythmService().validate(
            intents,
            cues,
            [_usage(intents[0], 0.6), _usage(intents[1], 0.2)],
        )


def test_explanatory_overlay_justifies_a_long_low_motion_hold():
    intents = [
        _intent(),
        _intent(
            start_ms=1_400,
            end_ms=4_400,
            visual_job="demonstrate_mechanism",
            shot_type="detail-insert",
            role="payoff",
            explanatory=True,
        ),
    ]
    cues = [_cue(0, 1_400, "three", "hearts"), _cue(1_400, 4_400, "pump", "blood")]

    report = EditorialRhythmService().validate(
        intents,
        cues,
        [_usage(intents[0], 0.6), _usage(intents[1], 0.2)],
    )

    assert report.passed is True
    assert report.low_motion_exceptions == (1,)
    assert report.loop_closure_ready is True


def test_rhythm_gate_rejects_a_cut_between_spoken_boundaries():
    intents = [
        _intent(end_ms=1_650),
        _intent(start_ms=1_650, end_ms=4_400, role="payoff"),
    ]
    cues = [_cue(0, 1_400, "three", "hearts"), _cue(1_400, 4_400, "pump", "blood")]

    with pytest.raises(EditorialRhythmError, match="beat_aligned=False"):
        EditorialRhythmService().validate(
            intents,
            cues,
            [_usage(intents[0], 0.6), _usage(intents[1], 0.6)],
        )
