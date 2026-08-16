from __future__ import annotations

from core.domain.entities.scene_plan import ScenePlan
from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.entities.timeline import Timeline
from core.domain.entities.voice_track import VoiceTrack
from core.domain.value_objects.premium_quality_report import (
    PremiumQualityCheck,
    PremiumQualityReport,
)


class PremiumShortsQualityService:
    def evaluate(
        self,
        *,
        voice_track: VoiceTrack,
        scene_plan: ScenePlan,
        timeline: Timeline,
        subtitle_track: SubtitleTrack,
    ) -> PremiumQualityReport:
        scene_durations = [
            scene.end_time - scene.start_time for scene in scene_plan.scenes
        ]
        asset_ids = [clip.asset.id for clip in timeline.clips]
        unique_asset_ratio = len(set(asset_ids)) / len(asset_ids) if asset_ids else 0.0
        adjacent_assets_are_unique = all(
            previous != current
            for previous, current in zip(asset_ids, asset_ids[1:])
        )
        max_cue_words = max(
            (len(cue.text.replace("\n", " ").split()) for cue in subtitle_track.cues),
            default=0,
        )
        max_cue_duration = max(
            (cue.end_time - cue.start_time for cue in subtitle_track.cues),
            default=0.0,
        )
        first_scene = scene_plan.scenes[0] if scene_plan.scenes else None
        hook_text = first_scene.narration.casefold() if first_scene else ""
        hook_markers = (
            "?",
            "imagine",
            "did you",
            "what if",
            "why",
            "how",
            "but",
            "secret",
            "surprising",
            "tiny",
            "giant",
            "never",
        )
        strong_hook = bool(first_scene) and (
            any(marker in hook_text for marker in hook_markers)
            or len(first_scene.narration.split()) <= 8
        )
        vertical_full_hd = all(
            (clip.asset.width or 0) >= 1080
            and (clip.asset.height or 0) >= 1920
            and (clip.asset.height or 0) > (clip.asset.width or 0)
            for clip in timeline.clips
        )
        checks = [
            PremiumQualityCheck(
                "minimum_duration",
                voice_track.duration_seconds >= 15.0,
                f"{voice_track.duration_seconds:.2f}s; minimum 15s",
            ),
            PremiumQualityCheck(
                "three_second_hook",
                strong_hook and bool(first_scene) and first_scene.end_time <= 3.2,
                f"hook ends at {first_scene.end_time if first_scene else 0.0:.2f}s",
            ),
            PremiumQualityCheck(
                "visual_beat_count",
                len(scene_plan.scenes) >= 5,
                f"{len(scene_plan.scenes)} scenes; minimum 5",
            ),
            PremiumQualityCheck(
                "maximum_scene_duration",
                bool(scene_durations) and max(scene_durations) <= 3.0,
                f"{max(scene_durations, default=0.0):.2f}s; maximum 3.0s",
            ),
            PremiumQualityCheck(
                "vertical_full_hd_sources",
                bool(timeline.clips) and vertical_full_hd,
                "every source must be portrait and at least 1080x1920",
            ),
            PremiumQualityCheck(
                "visual_variety",
                unique_asset_ratio >= 0.6 and adjacent_assets_are_unique,
                f"{unique_asset_ratio:.0%} unique assets; adjacent repeats: "
                f"{not adjacent_assets_are_unique}",
            ),
            PremiumQualityCheck(
                "caption_density",
                bool(subtitle_track.cues) and max_cue_words <= 4,
                f"maximum {max_cue_words} words per cue; limit 4",
            ),
            PremiumQualityCheck(
                "caption_pacing",
                bool(subtitle_track.cues) and max_cue_duration <= 3.0,
                f"maximum {max_cue_duration:.2f}s per cue; limit 3s",
            ),
        ]
        return PremiumQualityReport(
            passed=all(check.passed for check in checks),
            checks=checks,
        )
