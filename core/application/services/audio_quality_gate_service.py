"""Evidence-based, blocking 9/10 audio production gate."""
from __future__ import annotations

from core.domain.value_objects.audio_quality_report import (
    AudioQualityCheck,
    AudioQualityReport,
)
from core.domain.value_objects.background_track import BackgroundTrack
from core.domain.value_objects.media_inspection import MediaInspection
from core.domain.value_objects.media_quality_signals import MediaQualitySignals
from core.domain.value_objects.sound_design_plan import SoundDesignPlan


class AudioQualityGateService:
    threshold = 90

    def evaluate(
        self,
        *,
        plan: SoundDesignPlan,
        inspection: MediaInspection,
        signals: MediaQualitySignals,
        music_track: BackgroundTrack | None,
        voice_naturalness_score: int | None = None,
    ) -> AudioQualityReport:
        if voice_naturalness_score is not None and not 1 <= voice_naturalness_score <= 5:
            raise ValueError("voice_naturalness_score must be between 1 and 5.")
        checks: list[AudioQualityCheck] = []

        def add(name: str, category: str, points: int, maximum: int, passed: bool, blocking: bool, evidence: str, remediation: str) -> None:
            checks.append(AudioQualityCheck(name, category, points, maximum, passed, blocking, evidence, None if passed else remediation))

        loudness_ok = signals.integrated_lufs is not None and -15.0 <= signals.integrated_lufs <= -13.0
        add("integrated_loudness", "speech_mix", 15 if loudness_ok else 0, 15, loudness_ok, True, f"{signals.integrated_lufs} LUFS", "Remaster to -14 LUFS within a ±1 LU window.")
        peak_ok = signals.true_peak_dbfs is not None and signals.true_peak_dbfs <= -1.0 and not signals.clipping_detected
        add("true_peak_and_clipping", "speech_mix", 10 if peak_ok else 0, 10, peak_ok, True, f"Peak {signals.true_peak_dbfs} dBFS; clipping={signals.clipping_detected}", "Limit to -1.5 dBTP and remove clipping.")
        silence_ok = signals.maximum_silence_seconds <= 1.2 and signals.leading_silence_seconds <= 0.25 and signals.trailing_silence_seconds <= 0.5
        add("speech_continuity", "speech_mix", 10 if silence_ok else 0, 10, silence_ok, True, f"Maximum/leading/trailing silence: {signals.maximum_silence_seconds:.2f}/{signals.leading_silence_seconds:.2f}/{signals.trailing_silence_seconds:.2f}s", "Repair unexplained pauses and trim the head/tail.")

        delivery_ok = inspection.audio_sample_rate == 48_000 and inspection.audio_channels == 2 and (inspection.audio_bitrate or 0) >= 224_000
        add("delivery_format", "technical", 15 if delivery_ok else 0, 15, delivery_ok, True, f"{inspection.audio_sample_rate}Hz, {inspection.audio_channels}ch, {inspection.audio_bitrate}bps", "Encode 48 kHz stereo AAC at a 384 kbps target.")

        semantic = plan.semantic_kinds
        cue_coverage_ok = "hook_impact" in semantic and "payoff" in semantic and len(plan.cues) >= 2
        add("semantic_effect_coverage", "sound_effects", 10 if cue_coverage_ok else 0, 10, cue_coverage_ok, False, f"{len(plan.cues)} cues: {', '.join(sorted(semantic))}", "Add sparse hook and payoff cues tied to editorial meaning.")
        spacing_ok = all(right.timestamp_ms - left.timestamp_ms >= plan.minimum_cue_gap_ms for left, right in zip(plan.cues, plan.cues[1:]))
        add("effect_collision_policy", "sound_effects", 5 if spacing_ok else 0, 5, spacing_ok, True, f"Minimum permitted gap: {plan.minimum_cue_gap_ms}ms", "Remove overlapping or excessively dense effects.")

        ambience_ok = plan.ambience_profile != "none"
        add("ambience_layer", "ambience", 5 if ambience_ok else 0, 5, ambience_ok, False, f"Profile: {plan.ambience_profile}", "Choose a subtle semantic ambience profile.")
        music_ok = (
            music_track is not None and len(plan.music_automation) >= 2
        ) or (
            music_track is None and not plan.music_automation
        )
        add("music_direction_and_ducking", "music", 8 if music_ok else 0, 8, music_ok, False, f"Track: {music_track.title if music_track else 'intentional narration-only'}; automation points: {len(plan.music_automation)}", "Select a cleared track with automation, or explicitly choose narration-only.")

        dynamics_ok = signals.loudness_range_lu is None or 1.0 <= signals.loudness_range_lu <= 12.0
        add("mobile_dynamics", "mastering", 5 if dynamics_ok else 0, 5, dynamics_ok, False, f"LRA: {signals.loudness_range_lu if signals.loudness_range_lu is not None else 'not reported'} LU", "Keep loudness range between 1 and 12 LU.")
        rights_ok = music_track is None or (
            music_track.commercial_use
            and music_track.youtube_allowed
            and bool(music_track.license.strip())
            and bool(music_track.attribution.strip())
            and bool(music_track.sha256.strip())
            and bool(music_track.source_url.strip())
            and bool(music_track.evidence_reference.strip())
        )
        add("audio_rights_evidence", "rights", 7 if rights_ok else 0, 7, rights_ok, True, "Procedural layers are original; music evidence is complete." if rights_ok else "Music rights evidence is incomplete.", "Record source, commercial/YouTube permission, attribution, proof, and checksum.")
        voice_review_ok = voice_naturalness_score is not None and voice_naturalness_score >= 4
        add(
            "human_voice_performance",
            "speech_performance",
            10 if voice_review_ok else 0,
            10,
            voice_review_ok,
            False,
            (
                "Human listening review is pending."
                if voice_naturalness_score is None
                else f"Human voice performance score: {voice_naturalness_score}/5."
            ),
            "Listen for pronunciation, emphasis, pacing, emotion, and synthetic artifacts; record at least 4/5.",
        )

        score = sum(check.earned_points for check in checks)
        passed = score >= self.threshold and not any(check.blocking and not check.passed for check in checks)
        return AudioQualityReport(score, self.threshold, passed, tuple(checks))
