"""Full 100-point creative gate assembled from deterministic pipeline evidence."""
from __future__ import annotations

from collections.abc import Sequence

from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.creative_quality_report import (
    CreativeQualityCheck,
    CreativeQualityReport,
)
from core.domain.value_objects.media_inspection import MediaInspection
from core.domain.value_objects.media_quality_signals import MediaQualitySignals
from core.domain.value_objects.narrative_quality_report import NarrativeQualityReport
from core.domain.value_objects.retention_plan import RetentionPlan
from core.domain.value_objects.voice_direction import VoiceDirection
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.visual_intent import VisualIntent


class CreativeQualityGateService:
    """Score creative readiness without allowing totals to hide mandatory failures."""

    automatic_threshold = 85
    premium_threshold = 90

    def evaluate(
        self,
        *,
        narrative_report: NarrativeQualityReport,
        visual_intents: Sequence[VisualIntent],
        subtitle_cues: Sequence[SubtitleCue],
        source_assets: Sequence[MediaAsset],
        inspection: MediaInspection,
        quality_signals: MediaQualitySignals,
        fact_check_passed: bool,
        caption_ux_passed: bool,
        visual_relevance_passed: bool,
        sound_design_mode: str = "none",
        human_creative_approval: bool | None = None,
        voice_naturalness_score: int | None = None,
        retention_plan: RetentionPlan | None = None,
        voice_direction: VoiceDirection | None = None,
    ) -> CreativeQualityReport:
        if sound_design_mode not in {"none", "procedural", "licensed_music"}:
            raise ValueError("sound_design_mode must be none, procedural, or licensed_music.")
        if voice_naturalness_score is not None and not 1 <= voice_naturalness_score <= 5:
            raise ValueError("voice_naturalness_score must be between 1 and 5.")

        checks: list[CreativeQualityCheck] = []
        append = checks.append

        append(self._check(
            "grounded_factual_claims", "narrative", 5 if fact_check_passed else 0, 5,
            fact_check_passed, True,
            "Fact-check stage verified the final narration." if fact_check_passed else "Final narration lacks a verified fact-check artifact.",
            "Verify or rewrite every factual claim before narration generation.",
        ))
        narrative_points = round(
            (narrative_report.score / narrative_report.maximum_score) * 22
        ) if narrative_report.maximum_score else 0
        append(self._check(
            "narrative_contract", "narrative", narrative_points, 22,
            narrative_report.passed, True,
            f"Narrative score {narrative_report.score}/{narrative_report.maximum_score}; hook and payoff retained.",
            "Repair the hook, explicit answer, filler, or payoff issues in the narrative report.",
        ))
        retention_passed = retention_plan is None or retention_plan.passed
        retention_evidence = (
            "Compatibility evaluation: retention evidence was not supplied."
            if retention_plan is None
            else (
                f"Three hook options, {len(retention_plan.first_30_seconds)} opening-second "
                f"assignments, and {len(retention_plan.pattern_interrupts)} pattern interrupts."
            )
        )
        append(self._check(
            "retention_contract", "narrative", 3 if retention_passed else 0, 3,
            retention_passed, True,
            retention_evidence,
            "Regenerate three hooks, fill every opening second, and keep long-form visual changes within 20-30 seconds.",
        ))

        complete_jobs = sum(
            bool(intent.visual_job and intent.narration_text and intent.primary_keyword)
            for intent in visual_intents
        )
        visual_job_points = round(5 * complete_jobs / len(visual_intents)) if visual_intents else 0
        append(self._check(
            "visual_job_completeness", "visual_storytelling", visual_job_points, 5,
            bool(visual_intents) and complete_jobs == len(visual_intents), False,
            f"{complete_jobs}/{len(visual_intents)} beats declare a visual job and narration target.",
            "Give every narrative beat a filmable visual job and on-screen subject.",
        ))
        covered = min(len(source_assets), len(visual_intents))
        coverage_points = round(2 * covered / len(visual_intents)) if visual_intents else 0
        append(self._check(
            "asset_coverage", "visual_storytelling", coverage_points, 2,
            bool(visual_intents) and len(source_assets) >= len(visual_intents), False,
            f"{len(source_assets)} selected assets cover {len(visual_intents)} visual beats.",
            "Find a verified visual or explanatory graphic for every beat.",
        ))
        resolution_passed = bool(source_assets) and all(
            asset.width is not None
            and asset.height is not None
            and min(asset.width, asset.height) >= 720
            and max(asset.width, asset.height) >= 1280
            for asset in source_assets
        )
        low_resolution_assets = [
            asset.id
            for asset in source_assets
            if asset.width is None
            or asset.height is None
            or min(asset.width, asset.height) < 720
            or max(asset.width, asset.height) < 1280
        ]
        append(self._check(
            "source_resolution", "visual_storytelling", 2 if resolution_passed else 0, 2,
            resolution_passed, True,
            (
                "Every source visual is at least 720x1280 in its native orientation."
                if resolution_passed
                else f"Low or unknown source resolution: {', '.join(low_resolution_assets[:5]) or 'no assets'}."
            ),
            "Replace low-resolution sources before scaling them into the final master.",
        ))
        append(self._check(
            "dominant_visual_relevance", "visual_storytelling", 4 if visual_relevance_passed else 0, 4,
            visual_relevance_passed, True,
            "Vision selection completed without an unresolved dominant distractor." if visual_relevance_passed else "Visual relevance has not been verified.",
            "Replace the irrelevant dominant subject or use an explanatory graphic.",
        ))
        asset_ids = [asset.id for asset in source_assets]
        unique_ratio = len(set(asset_ids)) / len(asset_ids) if asset_ids else 0.0
        adjacent_unique = all(left != right for left, right in zip(asset_ids, asset_ids[1:]))
        diversity_passed = unique_ratio >= 0.6 and adjacent_unique
        append(self._check(
            "visual_diversity", "visual_storytelling", 2 if diversity_passed else (1 if unique_ratio >= 0.4 else 0), 2,
            diversity_passed, False,
            f"{unique_ratio:.0%} unique source assets; adjacent repeats: {not adjacent_unique}.",
            "Replace repeated clips or give reuse a materially different visual function.",
        ))

        first_intent = visual_intents[0] if visual_intents else None
        hook_pacing = bool(first_intent) and first_intent.narrative_role == "hook" and first_intent.start_ms == 0 and first_intent.duration_ms <= 1_300
        append(self._check(
            "immediate_hook_pacing", "editing_rhythm", 4 if hook_pacing else 0, 4,
            hook_pacing, False,
            f"Opening visual beat is {first_intent.duration_ms if first_intent else 0}ms.",
            "Put the promise in the first 1.3 seconds with an immediate visual change.",
            0.0,
        ))
        max_beat_ms = max((intent.duration_ms for intent in visual_intents), default=0)
        rhythm_passed = len(visual_intents) >= 5 and max_beat_ms <= 2_800
        rhythm_points = 6 if rhythm_passed else (3 if visual_intents and max_beat_ms <= 3_200 else 0)
        append(self._check(
            "semantic_cut_rhythm", "editing_rhythm", rhythm_points, 6,
            rhythm_passed, False,
            f"{len(visual_intents)} beats; longest visual beat {max_beat_ms}ms.",
            "Cut on information changes and shorten unresolved low-motion beats.",
        ))

        max_words = max((len(cue.text.replace("\n", " ").split()) for cue in subtitle_cues), default=0)
        density_passed = bool(subtitle_cues) and max_words <= 4
        append(self._check(
            "caption_density", "captions", 4 if density_passed else 0, 4,
            density_passed, False,
            f"Maximum caption density is {max_words} words.",
            "Repartition captions to a maximum of four words per cue.",
        ))
        max_cue_seconds = max((cue.end_time - cue.start_time for cue in subtitle_cues), default=0.0)
        cue_duration_passed = bool(subtitle_cues) and max_cue_seconds <= 2.2
        append(self._check(
            "caption_duration", "captions", 3 if cue_duration_passed else 0, 3,
            cue_duration_passed, False,
            f"Longest caption cue is {max_cue_seconds:.2f}s.",
            "Split long cues at sentence or clause boundaries.",
        ))
        timing_passed = bool(subtitle_cues) and all(
            current.start_time >= previous.end_time
            for previous, current in zip(subtitle_cues, subtitle_cues[1:])
        )
        append(self._check(
            "caption_timing", "captions", 2 if timing_passed else 0, 2,
            timing_passed, False,
            "Caption cues are ordered and non-overlapping." if timing_passed else "Caption cues overlap or are missing.",
            "Repair cue timing before render.",
        ))
        append(self._check(
            "caption_safe_zone", "captions", 1 if caption_ux_passed else 0, 1,
            caption_ux_passed, True,
            "Caption UX safe-zone validation passed." if caption_ux_passed else "Caption safe-zone validation is missing or failed.",
            "Resize or reposition the widest/lowest caption and regenerate previews.",
        ))

        lufs = quality_signals.integrated_lufs
        loudness_passed = lufs is not None and -16.0 <= lufs <= -13.0
        append(self._check(
            "narration_loudness", "narration_audio", 4 if loudness_passed else 0, 4,
            loudness_passed, False,
            f"Integrated loudness: {lufs if lufs is not None else 'unmeasured'} LUFS.",
            "Normalize the final mix into the -16 to -13 LUFS production range.",
        ))
        peak = quality_signals.true_peak_dbfs
        peak_passed = peak is not None and peak <= -1.0
        append(self._check(
            "true_peak", "narration_audio", 3 if peak_passed else 0, 3,
            peak_passed, False,
            f"True peak: {peak if peak is not None else 'unmeasured'} dBFS.",
            "Limit the final mix to a safe true peak no higher than -1 dBFS.",
        ))
        silence = quality_signals.maximum_silence_seconds
        pause_budget = (
            voice_direction.maximum_pause_ms / 1_000
            if voice_direction is not None
            else 0.55
        )
        pause_points = 3 if silence <= pause_budget else (1 if silence <= 1.2 else 0)
        append(self._check(
            "narration_pause_budget", "narration_audio", pause_points, 3,
            silence <= pause_budget, True,
            f"Longest detected narration gap: {silence:.2f}s; profile budget {pause_budget:.2f}s.",
            "Shorten unexplained pauses or record the editorial reason for the hold.",
        ))
        voice_points = 1 if voice_naturalness_score is None else (2 if voice_naturalness_score >= 4 else 0)
        append(self._check(
            "voice_naturalness", "narration_audio", voice_points, 2,
            voice_naturalness_score is not None and voice_naturalness_score >= 4, False,
            "Human voice review pending." if voice_naturalness_score is None else f"Human voice score: {voice_naturalness_score}/5.",
            "Review pronunciation, emphasis, pacing, and synthetic artifacts.",
        ))

        sound_points = {"none": 2, "procedural": 4, "licensed_music": 5}[sound_design_mode]
        append(self._check(
            "purposeful_sound_design", "sound_design", sound_points, 5,
            sound_points >= 4, False,
            f"Sound design mode: {sound_design_mode}.",
            "Add licensed music or semantic reveal/mechanism/payoff accents without masking speech.",
        ))

        vertical_passed = inspection.width >= 1080 and inspection.height >= 1920 and inspection.height > inspection.width
        append(self._check(
            "vertical_mobile_delivery", "technical", 3 if vertical_passed else 0, 3,
            vertical_passed, True,
            f"Rendered dimensions: {inspection.width}x{inspection.height}.",
            "Render a portrait 1080x1920 master.",
        ))
        codec_passed = inspection.video_codec == "h264" and inspection.audio_codec == "aac"
        append(self._check(
            "upload_codecs", "technical", 2 if codec_passed else 0, 2,
            codec_passed, True,
            f"Video/audio codecs: {inspection.video_codec}/{inspection.audio_codec or 'missing'}.",
            "Encode H.264 video with AAC audio.",
        ))
        fps_passed = 23.0 <= inspection.fps <= 60.0
        append(self._check(
            "standard_framerate", "technical", 1 if fps_passed else 0, 1,
            fps_passed, False,
            f"Frame rate: {inspection.fps:.2f} fps.",
            "Render at a standard progressive frame rate between 23 and 60 fps.",
        ))
        black_freeze_passed = quality_signals.opening_black_seconds <= 0.1 and quality_signals.maximum_freeze_seconds <= 4.0
        append(self._check(
            "black_and_freeze_scan", "technical", 2 if black_freeze_passed else 0, 2,
            black_freeze_passed, True,
            f"Opening black {quality_signals.opening_black_seconds:.2f}s; maximum freeze {quality_signals.maximum_freeze_seconds:.2f}s.",
            "Repair the opening frame or replace the frozen visual passage.",
        ))

        rights_passed = bool(source_assets) and all(asset.attribution.strip() and asset.license.strip() for asset in source_assets)
        append(self._check(
            "rights_metadata", "packaging", 3 if rights_passed else 0, 3,
            rights_passed, True,
            "Attribution and license metadata exist for every selected asset." if rights_passed else "One or more selected assets lack rights metadata.",
            "Replace the asset or record its attribution and YouTube usage rights.",
        ))
        append(self._check(
            "caption_package", "packaging", 1 if subtitle_cues else 0, 1,
            bool(subtitle_cues), True,
            f"{len(subtitle_cues)} caption cues are available for the sidecar track.",
            "Generate the language-specific sidecar caption file.",
        ))
        credits_passed = bool(source_assets) and all(asset.original_url.strip() for asset in source_assets)
        append(self._check(
            "source_traceability", "packaging", 1 if credits_passed else 0, 1,
            credits_passed, False,
            "Every visual has a source URL." if credits_passed else "Some source URLs are missing.",
            "Preserve the provider source URL in the upload package.",
        ))

        technical_post_render = (
            quality_signals.opening_black_seconds <= 0.1
            and quality_signals.total_black_seconds <= max(0.35, inspection.duration_seconds * 0.03)
            and quality_signals.maximum_freeze_seconds <= 4.0
            and quality_signals.maximum_silence_seconds <= 1.75
            and lufs is not None and -17.0 <= lufs <= -13.0
            and peak is not None and peak <= -1.0
        )
        append(self._check(
            "post_render_validation", "quality_control", 2 if technical_post_render else 0, 2,
            technical_post_render, True,
            "Post-render perceptual and loudness checks passed." if technical_post_render else "Post-render technical evidence contains a blocking failure.",
            "Repair the failed black, freeze, silence, loudness, or peak signal.",
        ))
        append(self._check(
            "human_creative_approval", "quality_control", 1 if human_creative_approval is True else 0, 1,
            human_creative_approval is True, False,
            "Human creative approval recorded." if human_creative_approval is True else "Human creative approval is pending.",
            "Watch the complete video and record final creative approval.",
        ))
        traceability_passed = bool(visual_intents and subtitle_cues and source_assets)
        append(self._check(
            "evidence_traceability", "quality_control", 2 if traceability_passed else 0, 2,
            traceability_passed, False,
            "Narration beats, captions, visual intents, and assets are traceable." if traceability_passed else "One or more production evidence layers are missing.",
            "Persist the missing beat, caption, visual, or asset evidence artifact.",
        ))

        score = sum(check.earned_points for check in checks)
        blocking_failures = any(check.blocking and not check.passed for check in checks)
        ready = score >= self.automatic_threshold and not blocking_failures
        premium = (
            ready
            and score >= self.premium_threshold
            and human_creative_approval is True
            and voice_naturalness_score is not None
            and voice_naturalness_score >= 4
        )
        return CreativeQualityReport(
            score=score,
            maximum_score=100,
            ready_to_upload=ready,
            premium_approved=premium,
            automatic_threshold=self.automatic_threshold,
            premium_threshold=self.premium_threshold,
            checks=tuple(checks),
            human_creative_approval=human_creative_approval,
            voice_naturalness_score=voice_naturalness_score,
        )

    @staticmethod
    def _check(
        name: str,
        category: str,
        earned_points: int,
        maximum_points: int,
        passed: bool,
        blocking: bool,
        evidence: str,
        remediation: str,
        timestamp_seconds: float | None = None,
    ) -> CreativeQualityCheck:
        return CreativeQualityCheck(
            name=name,
            category=category,
            earned_points=earned_points,
            maximum_points=maximum_points,
            passed=passed,
            blocking=blocking,
            evidence=evidence,
            remediation=None if passed else remediation,
            timestamp_seconds=timestamp_seconds,
        )
