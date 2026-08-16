from __future__ import annotations

import json
import re
import shutil
from dataclasses import replace
from collections.abc import Sequence
from pathlib import Path

from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.rendered_video import RenderedVideo
from core.domain.entities.script import Script
from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.exceptions import UploadPreparationError
from core.domain.ports.media_inspection_port import MediaInspectionPort
from core.domain.value_objects.media_inspection import MediaInspection
from core.domain.value_objects.creative_quality_report import CreativeQualityReport
from core.domain.value_objects.audio_quality_report import AudioQualityReport
from core.domain.value_objects.visual_quality_report import VisualQualityReport
from core.domain.value_objects.youtube_upload_package import (
    UploadReadinessCheck,
    YoutubeUploadPackage,
)
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.application.services.subtitle_formatter import SubtitleFormatter

MAX_SHORT_DURATION_SECONDS = 180.0
MAX_TITLE_CHARACTERS = 100
MAX_DESCRIPTION_CHARACTERS = 5000


class YoutubeUploadPackageService:
    def __init__(self, media_inspector: MediaInspectionPort) -> None:
        self._media_inspector = media_inspector

    async def prepare_factory_output(
        self,
        *,
        topic: str,
        script: Script,
        video_path: str,
        subtitle_cues: Sequence[SubtitleCue],
        source_assets: Sequence[MediaAsset],
        output_directory: str,
        language: str = "en",
        creative_quality_report: CreativeQualityReport | None = None,
        audio_quality_report: AudioQualityReport | None = None,
        visual_quality_report: VisualQualityReport | None = None,
    ) -> YoutubeUploadPackage:
        """Adapt durable factory artifacts into the public upload package."""
        inspection = await self._media_inspector.inspect(video_path)
        rendered_video = RenderedVideo.create(
            timeline_id=None,
            video_path=video_path,
            size_bytes=inspection.file_size_bytes,
            duration_seconds=inspection.duration_seconds,
            width=inspection.width,
            height=inspection.height,
            fps=inspection.fps,
        )
        package_dir = Path(output_directory).resolve()
        package_dir.mkdir(parents=True, exist_ok=True)
        normalized_cues = [
            replace(cue, index=index)
            for index, cue in enumerate(subtitle_cues, start=1)
        ]
        subtitle_track = SubtitleTrack.create(
            scene_plan_id=None,
            cues=normalized_cues,
        )
        staging_caption = package_dir / ".factory_captions.srt"
        staging_caption.write_text(
            SubtitleFormatter.format_srt(subtitle_track),
            encoding="utf-8",
        )
        try:
            return await self.prepare(
                topic=topic,
                script=script,
                rendered_video=rendered_video,
                subtitle_path=str(staging_caption),
                source_assets=source_assets,
                output_directory=str(package_dir),
                language=language,
                creative_quality_report=creative_quality_report,
                audio_quality_report=audio_quality_report,
                visual_quality_report=visual_quality_report,
                strict=True,
            )
        finally:
            staging_caption.unlink(missing_ok=True)

    async def prepare(
        self,
        *,
        topic: str,
        script: Script,
        rendered_video: RenderedVideo,
        subtitle_path: str,
        source_assets: Sequence[MediaAsset],
        output_directory: str,
        language: str = "en",
        made_for_kids: bool = False,
        creative_quality_report: CreativeQualityReport | None = None,
        audio_quality_report: AudioQualityReport | None = None,
        visual_quality_report: VisualQualityReport | None = None,
        strict: bool = True,
    ) -> YoutubeUploadPackage:
        package_dir = Path(output_directory).resolve()
        package_dir.mkdir(parents=True, exist_ok=True)

        source_video = Path(rendered_video.video_path)
        if not source_video.is_file():
            raise UploadPreparationError(
                f"Rendered video not found at '{rendered_video.video_path}'."
            )
        packaged_video = package_dir / "youtube_short.mp4"
        shutil.copyfile(source_video, packaged_video)
        source_subtitles = Path(subtitle_path)
        if not source_subtitles.is_file() or source_subtitles.stat().st_size <= 0:
            raise UploadPreparationError(
                f"Primary subtitle file is missing or empty at '{subtitle_path}'."
            )
        packaged_captions = package_dir / f"captions_{language}.srt"
        shutil.copyfile(source_subtitles, packaged_captions)

        inspection = await self._media_inspector.inspect(str(packaged_video))
        title = self._build_title(topic)
        credits = self._build_credits(source_assets)
        tags = self._build_tags(topic)
        description = self._build_description(script, credits, tags)

        frame_timestamp = self._thumbnail_timestamp(inspection.duration_seconds)
        thumbnail_frame = package_dir / "thumbnail_selection_frame.jpg"
        await self._media_inspector.extract_frame(
            str(packaged_video), str(thumbnail_frame), frame_timestamp
        )

        checks = self._build_checks(
            inspection=inspection,
            title=title,
            description=description,
            source_assets=source_assets,
            thumbnail_frame=thumbnail_frame,
            caption_file=packaged_captions,
        )
        if creative_quality_report is not None:
            checks = (*checks, self._check(
                "creative_quality_gate",
                creative_quality_report.ready_to_upload,
                True,
                f"{creative_quality_report.score}/{creative_quality_report.maximum_score}; "
                f"automatic threshold {creative_quality_report.automatic_threshold}",
            ))
        if audio_quality_report is not None:
            checks = (*checks, self._check(
                "audio_quality_gate",
                audio_quality_report.passed,
                True,
                f"{audio_quality_report.score}/100; required {audio_quality_report.threshold}",
            ))
        if visual_quality_report is not None:
            checks = (*checks, self._check(
                "visual_quality_gate",
                visual_quality_report.passed,
                True,
                f"{visual_quality_report.automatic_score}/90 automatic; "
                f"required {visual_quality_report.threshold}",
            ))
        ready_to_upload = not any(
            check.required and check.status == "FAIL" for check in checks
        )
        manual_checks = self._manual_checks()

        youtube_metadata = {
            "schema_version": 1,
            "platform": "youtube",
            "content_type": "short",
            "upload_file": packaged_video.name,
            "caption_file": packaged_captions.name,
            "title": title,
            "description": description,
            "tags": tags,
            "category_id": "27",
            "default_language": language,
            "privacy_status": "private",
            "made_for_kids": made_for_kids,
            "contains_paid_promotion": False,
            "ai_use_disclosure": "review_required",
            "thumbnail_selection": {
                "suggested_timestamp_seconds": frame_timestamp,
                "reference_frame": thumbnail_frame.name,
                "note": (
                    "YouTube Shorts does not accept a separately uploaded custom "
                    "thumbnail; select a frame during the upload flow."
                ),
            },
            "source_credits": credits,
            "ready_to_upload": ready_to_upload,
            "creative_quality": (
                creative_quality_report.to_dict()
                if creative_quality_report is not None
                else None
            ),
            "audio_quality": (
                audio_quality_report.to_dict()
                if audio_quality_report is not None
                else None
            ),
            "visual_quality": (
                visual_quality_report.to_dict()
                if visual_quality_report is not None
                else None
            ),
        }
        metadata_path = package_dir / "youtube_metadata.json"
        metadata_path.write_text(
            json.dumps(youtube_metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        quality_report = {
            "ready_to_upload": ready_to_upload,
            "inspection": inspection.to_dict(),
            "checks": [check.to_dict() for check in checks],
            "manual_checks": list(manual_checks),
            "creative_quality": (
                creative_quality_report.to_dict()
                if creative_quality_report is not None
                else None
            ),
            "audio_quality": (
                audio_quality_report.to_dict()
                if audio_quality_report is not None
                else None
            ),
            "visual_quality": (
                visual_quality_report.to_dict()
                if visual_quality_report is not None
                else None
            ),
        }
        quality_report_path = package_dir / "quality_report.json"
        quality_report_path.write_text(
            json.dumps(quality_report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        checklist_path = package_dir / "upload_checklist.md"
        checklist_path.write_text(
            self._format_checklist(checks, manual_checks), encoding="utf-8"
        )

        package = YoutubeUploadPackage(
            package_directory=str(package_dir),
            video_path=str(packaged_video),
            caption_path=str(packaged_captions),
            thumbnail_frame_path=str(thumbnail_frame),
            metadata_path=str(metadata_path),
            quality_report_path=str(quality_report_path),
            checklist_path=str(checklist_path),
            ready_to_upload=ready_to_upload,
            checks=checks,
            manual_checks=manual_checks,
        )
        if strict and not ready_to_upload:
            failed = ", ".join(
                check.name
                for check in checks
                if check.required and check.status == "FAIL"
            )
            raise UploadPreparationError(
                f"Video package failed required upload checks: {failed}. "
                f"See '{quality_report_path}'."
            )
        return package

    @staticmethod
    def _build_checks(
        *,
        inspection: MediaInspection,
        title: str,
        description: str,
        source_assets: Sequence[MediaAsset],
        thumbnail_frame: Path,
        caption_file: Path,
    ) -> tuple[UploadReadinessCheck, ...]:
        ratio = inspection.width / inspection.height if inspection.height else 0.0
        exact_vertical = abs(ratio - (9 / 16)) <= 0.02
        has_rights_metadata = bool(source_assets) and all(
            asset.attribution.strip() and asset.license.strip()
            for asset in source_assets
        )
        return (
            YoutubeUploadPackageService._check(
                "non_empty_file", inspection.file_size_bytes > 0, True,
                f"{inspection.file_size_bytes} bytes",
            ),
            YoutubeUploadPackageService._check(
                "shorts_duration",
                0 < inspection.duration_seconds <= MAX_SHORT_DURATION_SECONDS,
                True,
                f"{inspection.duration_seconds:.3f}s; maximum is 180s",
            ),
            YoutubeUploadPackageService._check(
                "vertical_9_16",
                exact_vertical and inspection.width < inspection.height,
                True,
                f"{inspection.width}x{inspection.height}",
            ),
            YoutubeUploadPackageService._check(
                "full_hd_vertical",
                inspection.width >= 1080 and inspection.height >= 1920,
                False,
                f"{inspection.width}x{inspection.height}; recommended 1080x1920+",
            ),
            YoutubeUploadPackageService._check(
                "mp4_container", "mp4" in inspection.format_names, True,
                ", ".join(inspection.format_names),
            ),
            YoutubeUploadPackageService._check(
                "h264_video", inspection.video_codec == "h264", True,
                inspection.video_codec or "missing",
            ),
            YoutubeUploadPackageService._check(
                "yuv420p_pixel_format", inspection.pixel_format == "yuv420p", True,
                inspection.pixel_format or "unknown",
            ),
            YoutubeUploadPackageService._check(
                "bt709_color_metadata",
                inspection.color_primaries == "bt709"
                and inspection.color_transfer == "bt709"
                and inspection.color_space == "bt709",
                True,
                (
                    f"primaries={inspection.color_primaries or 'unknown'}, "
                    f"transfer={inspection.color_transfer or 'unknown'}, "
                    f"space={inspection.color_space or 'unknown'}"
                ),
            ),
            YoutubeUploadPackageService._check(
                "progressive_scan", inspection.field_order == "progressive", True,
                inspection.field_order or "unknown",
            ),
            YoutubeUploadPackageService._check(
                "aac_audio", inspection.audio_codec == "aac", True,
                inspection.audio_codec or "missing audio stream",
            ),
            YoutubeUploadPackageService._check(
                "audio_48khz", inspection.audio_sample_rate == 48000, True,
                f"{inspection.audio_sample_rate or 0} Hz",
            ),
            YoutubeUploadPackageService._check(
                "stereo_audio", inspection.audio_channels == 2, True,
                f"{inspection.audio_channels or 0} channels",
            ),
            YoutubeUploadPackageService._check(
                "audio_bitrate",
                (inspection.audio_bitrate or 0) >= 224000,
                True,
                f"{inspection.audio_bitrate or 0} bps; measured minimum 224000",
            ),
            YoutubeUploadPackageService._check(
                "standard_framerate", 23.0 <= inspection.fps <= 60.0, False,
                f"{inspection.fps:.3f} fps",
            ),
            YoutubeUploadPackageService._check(
                "title_length", 0 < len(title) <= MAX_TITLE_CHARACTERS, True,
                f"{len(title)}/{MAX_TITLE_CHARACTERS} characters",
            ),
            YoutubeUploadPackageService._check(
                "description_length",
                0 < len(description) <= MAX_DESCRIPTION_CHARACTERS,
                True,
                f"{len(description)}/{MAX_DESCRIPTION_CHARACTERS} characters",
            ),
            YoutubeUploadPackageService._check(
                "source_rights_metadata", has_rights_metadata, True,
                "Attribution and license recorded for every selected visual",
            ),
            YoutubeUploadPackageService._check(
                "thumbnail_selection_frame",
                thumbnail_frame.is_file() and thumbnail_frame.stat().st_size > 0,
                True,
                thumbnail_frame.name,
            ),
            YoutubeUploadPackageService._check(
                "sidecar_captions",
                caption_file.is_file() and caption_file.stat().st_size > 0,
                True,
                caption_file.name,
            ),
        )

    @staticmethod
    def _check(
        name: str, passed: bool, required: bool, details: str
    ) -> UploadReadinessCheck:
        return UploadReadinessCheck(
            name=name,
            status="PASS" if passed else ("FAIL" if required else "WARN"),
            required=required,
            details=details,
        )

    @staticmethod
    def _build_title(topic: str) -> str:
        cleaned = " ".join(topic.split()).strip(" .") or "Untitled Short"
        suffix = " #Shorts"
        if "#shorts" in cleaned.casefold():
            return cleaned[:MAX_TITLE_CHARACTERS].rstrip()
        return f"{cleaned[: MAX_TITLE_CHARACTERS - len(suffix)].rstrip()}{suffix}"

    @staticmethod
    def _build_tags(topic: str) -> list[str]:
        stop_words = {
            "and", "are", "for", "from", "how", "the", "this", "what", "why",
            "bir", "bu", "da", "de", "ile", "için", "mi", "mı", "mu", "mü", "ve",
            "neden", "nasıl", "kaç", "var",
        }
        words = [
            word.lower()
            for word in re.findall(r"[\w'-]+", topic, flags=re.UNICODE)
            if len(word) > 2 and word.casefold() not in stop_words
        ]
        normalized = topic.casefold()
        semantic_tags: list[str] = []
        self_healing_markers = (
            "kendini onar", "onaran malzeme", "onaran polimer",
            "self-heal", "self heal",
        )
        if any(marker in normalized for marker in self_healing_markers):
            if any(character in normalized for character in "çğıöşü") or "kendini" in normalized:
                semantic_tags.extend(
                    [
                        "kendini onaran malzeme",
                        "kendini onaran polimer",
                        "NASA teknolojisi",
                        "akıllı malzemeler",
                        "malzeme bilimi",
                        "geleceğin teknolojileri",
                        "self healing materials",
                    ]
                )
            else:
                semantic_tags.extend(
                    [
                        "self healing materials",
                        "self healing polymers",
                        "smart materials",
                        "materials science",
                        "NASA technology",
                        "future technology",
                    ]
                )
        tags = [
            "Shorts",
            topic.strip(),
            "educational shorts",
            *semantic_tags,
            *words,
        ]
        return list(dict.fromkeys(tag for tag in tags if tag))[:15]

    @staticmethod
    def _build_credits(source_assets: Sequence[MediaAsset]) -> list[dict[str, str]]:
        credits: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for asset in source_assets:
            key = (asset.provider, asset.provider_asset_id)
            if key in seen:
                continue
            seen.add(key)
            credits.append(
                {
                    "provider": asset.provider,
                    "asset_id": asset.provider_asset_id,
                    "attribution": asset.attribution,
                    "license": asset.license,
                    "source_url": asset.original_url,
                }
            )
        return credits

    @staticmethod
    def _build_description(
        script: Script, credits: Sequence[dict[str, str]], tags: Sequence[str]
    ) -> str:
        summary = " ".join(script.full_text.split())[:700].rstrip()
        credit_lines = list(dict.fromkeys(
            f"- {credit['attribution']} ({credit['license']})"
            for credit in credits
        ))
        hashtag_values = [
            re.sub(r"[^\w]", "", tag)
            for tag in tags
            if not re.search(r"\s", tag)
        ][:5]
        hashtags = " ".join(f"#{value}" for value in hashtag_values if value)
        sections = [summary]
        if credit_lines:
            sections.append("Visual credits:\n" + "\n".join(credit_lines))
        sections.append(hashtags)
        return "\n\n".join(section for section in sections if section)[
            :MAX_DESCRIPTION_CHARACTERS
        ]

    @staticmethod
    def _thumbnail_timestamp(duration_seconds: float) -> float:
        if duration_seconds <= 0.2:
            return 0.0
        return round(min(max(duration_seconds * 0.02, 0.5), duration_seconds - 0.1), 3)

    @staticmethod
    def _manual_checks() -> tuple[str, ...]:
        return (
            "Watch the complete MP4 and confirm narration, cuts, and captions are correct.",
            "Confirm every visual and audio element is licensed for YouTube use.",
            "Review the title, description, tags, audience, and private visibility setting.",
            "Choose a frame during Shorts upload; custom thumbnail files are not supported.",
            "Set YouTube's AI use disclosure according to the final realistic content.",
        )

    @staticmethod
    def _format_checklist(
        checks: Sequence[UploadReadinessCheck], manual_checks: Sequence[str]
    ) -> str:
        automated = "\n".join(
            f"- [{'x' if check.status == 'PASS' else ' '}] "
            f"{check.name}: {check.status} — {check.details}"
            for check in checks
        )
        manual = "\n".join(f"- [ ] {item}" for item in manual_checks)
        return (
            "# YouTube Shorts Upload Checklist\n\n"
            "## Automated Checks\n"
            f"{automated}\n\n"
            "## Manual Review\n"
            f"{manual}\n"
        )
