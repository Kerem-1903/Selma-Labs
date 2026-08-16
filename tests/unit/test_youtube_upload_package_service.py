from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.application.services.youtube_upload_package_service import (
    YoutubeUploadPackageService,
)
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.rendered_video import RenderedVideo
from core.domain.entities.script import Script
from core.domain.exceptions import UploadPreparationError
from core.domain.value_objects.media_inspection import MediaInspection
from core.domain.value_objects.creative_quality_report import (
    CreativeQualityCheck,
    CreativeQualityReport,
)
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.word_timing import WordTiming


def _script(topic: str = "Why the ocean glows at night") -> Script:
    return Script.create(
        topic=topic,
        full_text=(
            "Some ocean organisms create light through bioluminescence. "
            "The reaction helps them communicate, hunt, and avoid predators."
        ),
        target_duration_seconds=30,
        provider_used="fake",
    )


def _rendered_video(path: Path) -> RenderedVideo:
    return RenderedVideo(
        id="video-1",
        timeline_id="timeline-1",
        video_path=str(path),
        size_bytes=path.stat().st_size,
        duration_seconds=30.0,
        width=1080,
        height=1920,
        fps=30.0,
        created_at=datetime.now(timezone.utc),
    )


def _asset() -> MediaAsset:
    return MediaAsset(
        id="pexels:1",
        provider="pexels",
        provider_asset_id="1",
        media_type="video",
        original_url="https://www.pexels.com/video/1/",
        thumbnail_url="https://images.pexels.com/1.jpg",
        width=1080,
        height=1920,
        duration_seconds=10.0,
        fps=30.0,
        tags=["ocean"],
        attribution="Video by Test Creator on Pexels",
        license="Pexels License",
    )


class FakeMediaInspector:
    def __init__(
        self,
        *,
        width: int = 1080,
        height: int = 1920,
        bt709: bool = True,
    ) -> None:
        self.width = width
        self.height = height
        self.bt709 = bt709

    async def inspect(self, video_path: str) -> MediaInspection:
        return MediaInspection(
            format_names=("mov", "mp4"),
            duration_seconds=30.0,
            width=self.width,
            height=self.height,
            fps=30.0,
            video_codec="h264",
            pixel_format="yuv420p",
            audio_codec="aac",
            audio_sample_rate=48000,
            audio_bitrate=320000,
            file_size_bytes=Path(video_path).stat().st_size,
            color_primaries="bt709" if self.bt709 else None,
            color_transfer="bt709" if self.bt709 else None,
            color_space="bt709" if self.bt709 else None,
            color_range="tv",
            field_order="progressive",
            audio_channels=2,
        )

    async def extract_frame(
        self, video_path: str, output_path: str, timestamp_seconds: float
    ) -> None:
        del video_path, timestamp_seconds
        Path(output_path).write_bytes(b"jpeg-frame")


@pytest.mark.asyncio
async def test_prepare_creates_complete_upload_package(tmp_path):
    source_video = tmp_path / "rendered.mp4"
    source_video.write_bytes(b"valid-video-bytes")
    subtitles = tmp_path / "captions.srt"
    subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n", encoding="utf-8")
    package_dir = tmp_path / "publish"
    service = YoutubeUploadPackageService(FakeMediaInspector())

    package = await service.prepare(
        topic="Why the ocean glows at night",
        script=_script(),
        rendered_video=_rendered_video(source_video),
        subtitle_path=str(subtitles),
        source_assets=[_asset()],
        output_directory=str(package_dir),
    )

    assert package.ready_to_upload is True
    assert (package_dir / "youtube_short.mp4").read_bytes() == b"valid-video-bytes"
    assert (package_dir / "thumbnail_selection_frame.jpg").is_file()
    assert (package_dir / "captions_en.srt").is_file()
    assert (package_dir / "quality_report.json").is_file()
    assert (package_dir / "upload_checklist.md").is_file()
    metadata = json.loads(
        (package_dir / "youtube_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["title"].endswith("#Shorts")
    assert len(metadata["title"]) <= 100
    assert metadata["privacy_status"] == "private"
    assert metadata["ready_to_upload"] is True
    assert metadata["source_credits"][0]["provider"] == "pexels"


def test_turkish_hashtags_skip_question_words_and_full_phrase_slug():
    service = YoutubeUploadPackageService(FakeMediaInspector())
    tags = service._build_tags("Ahtapotların neden üç kalbi var?")
    description = service._build_description(_script(), [], tags)

    assert "#Ahtapotlarınnedenüçkalbivar" not in description
    assert "#neden" not in description
    assert "#var" not in description
    assert "#Shorts" in description
    assert "#ahtapotların" in description


def test_builds_semantic_tags_for_turkish_self_healing_materials():
    tags = YoutubeUploadPackageService(FakeMediaInspector())._build_tags(
        "Kendini Onaran Malzemeler"
    )

    assert "kendini onaran polimer" in tags
    assert "NASA teknolojisi" in tags
    assert "malzeme bilimi" in tags
    assert "self healing materials" in tags


@pytest.mark.asyncio
async def test_prepare_factory_output_builds_sidecar_captions_and_package(tmp_path):
    source_video = tmp_path / "rendered.mp4"
    source_video.write_bytes(b"valid-video-bytes")
    cue = SubtitleCue.from_words(
        [
            WordTiming("Ahtapotların", 0, 500),
            WordTiming("üç", 510, 700),
            WordTiming("kalbi", 710, 1_000),
        ]
    )
    package_dir = tmp_path / "factory-publish"

    package = await YoutubeUploadPackageService(
        FakeMediaInspector()
    ).prepare_factory_output(
        topic="Ahtapotların üç kalbi",
        script=_script("Ahtapotların üç kalbi"),
        video_path=str(source_video),
        subtitle_cues=[cue],
        source_assets=[_asset()],
        output_directory=str(package_dir),
        language="tr",
    )

    captions = (package_dir / "captions_tr.srt").read_text(encoding="utf-8")
    assert package.ready_to_upload is True
    assert "00:00:00,000 --> 00:00:01,000" in captions
    assert "Ahtapotların üç kalbi" in captions
    assert not (package_dir / ".factory_captions.srt").exists()


@pytest.mark.asyncio
async def test_prepare_rejects_non_vertical_video_in_strict_mode(tmp_path):
    source_video = tmp_path / "landscape.mp4"
    source_video.write_bytes(b"video")
    subtitles = tmp_path / "captions.srt"
    subtitles.write_text("captions", encoding="utf-8")
    package_dir = tmp_path / "publish"
    service = YoutubeUploadPackageService(
        FakeMediaInspector(width=1920, height=1080)
    )

    with pytest.raises(UploadPreparationError, match="vertical_9_16"):
        await service.prepare(
            topic="Landscape video",
            script=_script("Landscape video"),
            rendered_video=_rendered_video(source_video),
            subtitle_path=str(subtitles),
            source_assets=[_asset()],
            output_directory=str(package_dir),
        )

    report = json.loads(
        (package_dir / "quality_report.json").read_text(encoding="utf-8")
    )
    assert report["ready_to_upload"] is False


@pytest.mark.asyncio
async def test_prepare_blocks_missing_bt709_delivery_metadata(tmp_path):
    source_video = tmp_path / "rendered.mp4"
    source_video.write_bytes(b"video")
    subtitles = tmp_path / "captions.srt"
    subtitles.write_text("captions", encoding="utf-8")

    with pytest.raises(UploadPreparationError, match="bt709_color_metadata"):
        await YoutubeUploadPackageService(FakeMediaInspector(bt709=False)).prepare(
            topic="Color metadata test",
            script=_script("Color metadata test"),
            rendered_video=_rendered_video(source_video),
            subtitle_path=str(subtitles),
            source_assets=[_asset()],
            output_directory=str(tmp_path / "publish-color"),
        )


@pytest.mark.asyncio
async def test_prepare_requires_source_rights_metadata(tmp_path):
    source_video = tmp_path / "rendered.mp4"
    source_video.write_bytes(b"video")
    subtitles = tmp_path / "captions.srt"
    subtitles.write_text("captions", encoding="utf-8")
    service = YoutubeUploadPackageService(FakeMediaInspector())
    asset = _asset()
    asset_without_rights = MediaAsset(
        **{**asset.__dict__, "attribution": "", "license": ""}
    )

    with pytest.raises(UploadPreparationError, match="source_rights_metadata"):
        await service.prepare(
            topic="Rights test",
            script=_script("Rights test"),
            rendered_video=_rendered_video(source_video),
            subtitle_path=str(subtitles),
            source_assets=[asset_without_rights],
            output_directory=str(tmp_path / "publish"),
        )


@pytest.mark.asyncio
async def test_prepare_blocks_creative_score_below_automatic_threshold(tmp_path):
    source_video = tmp_path / "rendered.mp4"
    source_video.write_bytes(b"video")
    subtitles = tmp_path / "captions.srt"
    subtitles.write_text("captions", encoding="utf-8")
    creative_report = CreativeQualityReport(
        score=84,
        maximum_score=100,
        ready_to_upload=False,
        premium_approved=False,
        automatic_threshold=85,
        premium_threshold=90,
        checks=(
            CreativeQualityCheck(
                name="aggregate_fixture",
                category="fixture",
                earned_points=84,
                maximum_points=100,
                passed=False,
                blocking=False,
                evidence="Fixture score below threshold.",
                remediation="Improve the weakest creative category.",
            ),
        ),
    )

    with pytest.raises(UploadPreparationError, match="creative_quality_gate"):
        await YoutubeUploadPackageService(FakeMediaInspector()).prepare(
            topic="Creative gate test",
            script=_script("Creative gate test"),
            rendered_video=_rendered_video(source_video),
            subtitle_path=str(subtitles),
            source_assets=[_asset()],
            output_directory=str(tmp_path / "publish-creative"),
            creative_quality_report=creative_report,
        )
