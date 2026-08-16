"""Fail-closed visual-edit scoring using plan, source, and rendered evidence."""
from __future__ import annotations

from collections.abc import Sequence

from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.asset_diversity import AssetUsage
from core.domain.value_objects.media_quality_signals import MediaQualitySignals
from core.domain.value_objects.visual_edit_plan import VisualEditPlan
from core.domain.value_objects.visual_intent import VisualIntent
from core.domain.value_objects.visual_quality_report import (
    VisualQualityCheck,
    VisualQualityReport,
)


class VisualQualityGateService:
    """Award 90 objective points and reserve 10 points for a human taste pass."""

    def __init__(self, *, threshold: int = 90) -> None:
        if not 0 <= threshold <= 90:
            raise ValueError("Automatic visual threshold must be between 0 and 90.")
        self.threshold = threshold

    def evaluate(
        self,
        *,
        plan: VisualEditPlan,
        visual_intents: Sequence[VisualIntent],
        source_assets: Sequence[MediaAsset],
        asset_usages: Sequence[AssetUsage],
        quality_signals: MediaQualitySignals,
        human_taste_score: int | None = None,
    ) -> VisualQualityReport:
        checks: list[VisualQualityCheck] = []

        def add(
            name: str,
            category: str,
            points: int,
            passed: bool,
            blocking: bool,
            evidence: str,
            remediation: str,
        ) -> None:
            checks.append(
                VisualQualityCheck(
                    name=name,
                    category=category,
                    earned_points=points if passed else 0,
                    maximum_points=points,
                    passed=passed,
                    blocking=blocking,
                    evidence=evidence,
                    remediation=None if passed else remediation,
                )
            )

        coverage_passed = (
            len(plan.beats) == len(visual_intents)
            and len(source_assets) >= len(plan.beats)
            and (not asset_usages or len(asset_usages) == len(plan.beats))
        )
        add(
            "storyboard_asset_coverage", "coverage", 8, coverage_passed, True,
            f"{len(plan.beats)} planned beats, {len(source_assets)} assets, "
            f"{len(asset_usages)} usage records.",
            "Provide one verified source and usage record for every planned beat.",
        )

        first = plan.beats[0]
        hook_passed = first.purpose == "promise" and first.duration_ms <= 1_300
        add(
            "first_second_promise", "retention", 10, hook_passed, True,
            f"Opening purpose={first.purpose}; duration={first.duration_ms}ms.",
            "Open on the promised result or contradiction within 1.3 seconds.",
        )

        semantic_passed = bool(visual_intents) and all(
            intent.primary_keyword
            and intent.narration_text
            and intent.visual_job
            and not set(intent.required_subjects).intersection(
                intent.forbidden_dominant_subjects
            )
            for intent in visual_intents
        )
        add(
            "semantic_visual_jobs", "relevance", 10, semantic_passed, True,
            "Every beat declares its narration target, visual job, and subject policy."
            if semantic_passed else "One or more beats have incomplete semantic evidence.",
            "Regenerate the incomplete visual intent or replace its dominant subject.",
        )

        rights_passed = bool(source_assets) and all(
            asset.license.strip()
            and asset.attribution.strip()
            and asset.original_url.strip()
            for asset in source_assets
        )
        add(
            "visual_rights_evidence", "rights", 8, rights_passed, True,
            "License, attribution, and source URL exist for every visual."
            if rights_passed else "At least one visual is missing rights evidence.",
            "Replace the source or persist its license, attribution, and original URL.",
        )

        low_resolution = [
            asset.id
            for asset in source_assets
            if asset.width is None
            or asset.height is None
            or min(asset.width, asset.height) < 720
            or max(asset.width, asset.height) < 1280
        ]
        resolution_passed = bool(source_assets) and not low_resolution
        add(
            "native_source_resolution", "source_quality", 8, resolution_passed, True,
            "Every visual is at least 720x1280 before crop."
            if resolution_passed else f"Low or unknown resolution: {', '.join(low_resolution[:6])}.",
            "Replace low-resolution footage before it reaches the renderer.",
        )

        asset_ids = [asset.id for asset in source_assets[: len(plan.beats)]]
        unique_ratio = len(set(asset_ids)) / len(asset_ids) if asset_ids else 0.0
        adjacent_unique = all(a != b for a, b in zip(asset_ids, asset_ids[1:]))
        diversity_passed = bool(asset_ids) and unique_ratio >= 0.60 and adjacent_unique
        add(
            "perceptual_source_diversity", "diversity", 10, diversity_passed, True,
            f"Unique source ratio={unique_ratio:.0%}; adjacent repeats={not adjacent_unique}.",
            "Replace adjacent repeats and keep reused sources below the finite budget.",
        )

        continuous = all(
            current.end_ms == following.start_ms
            for current, following in zip(plan.beats, plan.beats[1:])
        )
        longest_beat = max(beat.duration_ms for beat in plan.beats)
        rhythm_passed = continuous and longest_beat <= plan.maximum_visual_hold_ms
        add(
            "information_change_rhythm", "rhythm", 10, rhythm_passed, True,
            f"Longest hold={longest_beat}ms; budget={plan.maximum_visual_hold_ms}ms; "
            f"continuous={continuous}.",
            "Cut at the next information beat or add a justified explanatory interrupt.",
        )

        expected = plan.expected_cut_count
        detected = len(quality_signals.scene_change_timestamps_seconds)
        minimum_detected = 0 if expected == 0 else max(1, round(expected * 0.55))
        # Scene detection can merge two semantically similar hard cuts (for
        # example, two adjacent airplane views). Keep a bounded detector
        # tolerance while the independent freeze scan remains fail-closed.
        stasis_budget = max(4.5, plan.maximum_visual_hold_ms / 1_000 + 1.7)
        rendered_change_passed = (
            detected >= minimum_detected
            and quality_signals.maximum_visual_stasis_seconds <= stasis_budget
            and quality_signals.maximum_freeze_seconds <= 4.0
        )
        add(
            "rendered_visual_change", "render_evidence", 12,
            rendered_change_passed, True,
            f"Detected cuts={detected}/{expected} planned; longest visual stasis="
            f"{quality_signals.maximum_visual_stasis_seconds:.2f}s; budget={stasis_budget:.2f}s.",
            "Repair missing cuts, replace the frozen passage, or lower an overly soft transition.",
        )

        shots = [beat.shot_type for beat in plan.beats]
        motions = [beat.motion_type for beat in plan.beats]
        transitions = [beat.transition for beat in plan.beats]
        no_shot_repeat = all(a != b for a, b in zip(shots, shots[1:]))
        no_three_motion = all(
            len(set(motions[index : index + 3])) > 1
            for index in range(max(0, len(motions) - 2))
        )
        non_hard = sum(value != "hard" for value in transitions)
        no_adjacent_effects = all(
            left == "hard" or right == "hard"
            for left, right in zip(transitions, transitions[1:])
        )
        grammar_passed = (
            no_shot_repeat
            and no_three_motion
            and non_hard <= plan.non_hard_transition_budget
            and no_adjacent_effects
        )
        add(
            "shot_motion_transition_grammar", "edit_grammar", 8,
            grammar_passed, False,
            f"Shot repeats={not no_shot_repeat}; three-beat motion runs={not no_three_motion}; "
            f"semantic transitions={non_hard}/{plan.non_hard_transition_budget}.",
            "Alternate shot scale or motion and reserve effects for semantic changes.",
        )

        explanatory = [intent for intent in visual_intents if intent.explanatory_required]
        explanation_passed = all(
            intent.explanation_mode in {"overlay", "diagram", "hybrid"}
            and 0 < len(intent.overlay_labels) <= 3
            for intent in explanatory
        ) and all(beat.safe_zone == "center_subject_caption_clear" for beat in plan.beats)
        add(
            "explanation_and_mobile_safe_zone", "mobile_clarity", 6,
            explanation_passed, True,
            f"{len(explanatory)} explanatory beats use bounded labels; safe zones declared.",
            "Replace generic stock with a diagram/callout and keep labels out of caption/UI zones.",
        )

        automatic_score = sum(check.earned_points for check in checks)
        score = automatic_score + (human_taste_score or 0)
        passed = automatic_score >= self.threshold and not any(
            check.blocking and not check.passed for check in checks
        )
        return VisualQualityReport(
            score=score,
            threshold=self.threshold,
            passed=passed,
            checks=tuple(checks),
            human_taste_score=human_taste_score,
        )
