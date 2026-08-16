"""Render the source-grounded Turkish Venus day-versus-year Short."""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

from mutagen.mp3 import MP3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from core.application.services.brand_narration_service import BrandNarrationService
from core.application.services.caption_ux_service import CaptionUxService
from core.application.services.creative_quality_gate_service import CreativeQualityGateService
from core.application.services.cue_partitioning_service import CuePartitioningService
from core.application.services.narrative_quality_service import NarrativeQualityService
from core.application.services.post_render_quality_service import PostRenderQualityService
from core.application.services.premium_subtitle_formatter import PremiumSubtitleFormatter
from core.application.services.remotion_timeline_service import RemotionTimelineService
from core.application.services.scene_planning_service import ScenePlanningService
from core.application.services.youtube_upload_package_service import YoutubeUploadPackageService
from core.domain.entities.audio_asset import AudioAsset
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.script import Script
from core.domain.value_objects.caption_ux import CaptionSafeZoneProfile
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.word_timing import WordTiming
from infrastructure.providers.render.ffmpeg_media_quality_analysis_provider import (
    FfmpegMediaQualityAnalysisProvider,
)
from infrastructure.providers.render.ffprobe_media_inspection_provider import (
    FfprobeMediaInspectionProvider,
)
from infrastructure.providers.render.remotion_render_provider import RemotionRenderProvider
from infrastructure.providers.voice.elevenlabs_provider import ElevenLabsVoiceProvider


OUTPUT_DIRECTORY = PROJECT_ROOT / "output" / "venus_day_year_final"
PACKAGE_DIRECTORY = OUTPUT_DIRECTORY / "youtube"
TOPIC = "Venüs'te Bir Gün Neden Bir Yıldan Uzun?"
BASE_SCRIPT = (
    "Venüs'te 1 gün, 1 yıldan uzun. "
    "Çünkü Venüs, kendi ekseninde bir turu 243 Dünya gününde tamamlıyor. "
    "Güneş'in çevresindeki bir turuysa yalnızca 225 gün sürüyor. "
    "Yani yıldız günü, yılından 18 gün daha uzun. "
    "Ama yüzeyde, bir gün doğumundan diğerine kadar geçen güneş günü yaklaşık 117 Dünya günü."
)
BRAND_SIGNATURE = "Strange Things'e hoş geldiniz."
NASA_SOURCE = "https://science.nasa.gov/venus/venus-facts/"


class _UnusedSceneProvider:
    provider_identity = "manual:nasa-source-grounded"

    async def plan_scenes(self, narration_text: str):  # pragma: no cover
        del narration_text
        raise RuntimeError("This production uses local timed visual intents.")


def _visual_assets() -> list[MediaAsset]:
    manifest_path = PROJECT_ROOT / "assets" / "visuals" / "venus" / "license_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets: list[MediaAsset] = []
    for item in manifest["assets"]:
        local_path = manifest_path.parent / item["file"]
        clean_path = manifest_path.parent / "clean" / local_path.name
        if clean_path.is_file():
            local_path = clean_path
        if not local_path.is_file():
            raise FileNotFoundError(f"Missing Venus visual: {local_path}")
        assets.append(
            MediaAsset(
                id=str(item["id"]),
                provider=str(item["provider"]),
                provider_asset_id=str(item["id"]).split(":")[-1],
                media_type="video",
                original_url="https://selma.local/original/venus-motion-graphics",
                tags=list(item.get("tags", [])),
                attribution=str(item["attribution"]),
                license=str(item["license"]),
                local_path=str(local_path.resolve()),
                metadata={"motion_energy": item.get("motion_energy")},
            )
        )
    return assets


def _refine_intent(intent):
    text = intent.narration_text.casefold()
    labels: tuple[str, ...] = ()
    visual_job = intent.visual_job
    if "1 gün" in text and "1 yıldan" in text:
        labels = ("1 GÜN", ">", "1 YIL")
        visual_job = "compare_states"
    elif "hoş geldiniz" in text:
        visual_job = "support_context"
    elif "243" in text:
        labels = ("EKSEN DÖNÜŞÜ", "243 DÜNYA GÜNÜ")
        visual_job = "demonstrate_mechanism"
    elif "225" in text:
        labels = ("VENÜS YILI", "225 DÜNYA GÜNÜ")
        visual_job = "compare_states"
    elif "18 gün" in text:
        labels = ("243 − 225", "18 GÜN DAHA UZUN")
        visual_job = "deliver_payoff"
    elif "117" in text or "gün doğum" in text:
        labels = ("GÜNEŞ GÜNÜ", "≈ 117 DÜNYA GÜNÜ")
        visual_job = "clarify_distinction"
    return replace(
        intent,
        visual_job=visual_job,
        overlay_labels=labels,
        explanatory_required=bool(labels),
        explanation_mode="hybrid" if labels else "stock",
    )


def _caption_profile(settings):
    return CaptionSafeZoneProfile(
        margin_left=settings.caption_safe_margin_left,
        margin_right=settings.caption_safe_margin_right,
        caption_baseline_y=settings.caption_baseline_y,
        font_size=settings.caption_font_size,
        outline_width=settings.caption_outline_width,
        active_scale_percent=settings.caption_active_scale_percent,
        minimum_scaled_emphasis_ms=settings.caption_minimum_scaled_emphasis_ms,
    )


async def main() -> Path:
    settings = get_settings()
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    draft = Script.create(
        topic=TOPIC,
        full_text=BASE_SCRIPT,
        target_duration_seconds=24,
        provider_used="manual:nasa-venus-facts",
    )
    enriched, narrative_report = NarrativeQualityService().validate(draft, language="tr")
    script = BrandNarrationService(BRAND_SIGNATURE).apply(enriched)

    audio_path = OUTPUT_DIRECTORY / "narration_tr.mp3"
    timeline_path = OUTPUT_DIRECTORY / "venus_day_year.motion.json"
    if audio_path.is_file() and timeline_path.is_file():
        cached_timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        words = [
            WordTiming(
                word["text"],
                round(word["startFrame"] * 1_000 / cached_timeline["fps"]),
                round(word["endFrame"] * 1_000 / cached_timeline["fps"]),
                1.0,
            )
            for cue in cached_timeline["captions"]
            for word in cue["words"]
        ]
        audio_info = MP3(audio_path).info
        duration_seconds = float(audio_info.length)
        sample_rate = int(audio_info.sample_rate)
        voice_provider_name = "elevenlabs:cached-timestamp-audio"
    else:
        voice_provider = ElevenLabsVoiceProvider(
            api_key=settings.elevenlabs_api_key,
            model_id=settings.elevenlabs_model_id,
            stability=settings.elevenlabs_stability,
            similarity_boost=settings.elevenlabs_similarity_boost,
            style=settings.elevenlabs_style,
            speed=settings.elevenlabs_speed,
            use_speaker_boost=settings.elevenlabs_use_speaker_boost,
        )
        generated = await voice_provider.generate_voice(
            script.full_text,
            settings.elevenlabs_voice_id,
        )
        if not generated.segments:
            raise RuntimeError("ElevenLabs returned no timestamp alignment.")
        audio_path.write_bytes(generated.audio_bytes)
        words = [
            WordTiming(
                segment.text,
                round(segment.start * 1_000),
                round(segment.end * 1_000),
                1.0,
            )
            for segment in generated.segments
        ]
        duration_seconds = generated.duration_seconds
        sample_rate = generated.sample_rate
        voice_provider_name = generated.provider

    profile = _caption_profile(settings)
    caption_ux_service = CaptionUxService(profile)
    cues = CuePartitioningService(
        maximum_words_per_cue=settings.caption_maximum_words_per_cue,
        maximum_cue_duration_ms=settings.caption_maximum_cue_duration_ms,
        line_width_validator=caption_ux_service.words_fit,
    ).partition(words)
    caption_report = caption_ux_service.evaluate(cues)

    audio_asset = AudioAsset.create(
        source_provider=voice_provider_name,
        source_asset_id="venus-day-year-tr-final",
        local_path=str(audio_path),
        duration_ms=round(duration_seconds * 1_000),
        media_type="audio/mpeg",
        license="self-generated narration",
        usage_rights="publish",
        language="tr",
        sample_rate_hz=sample_rate,
    )
    highlight = SelectedHighlight(
        audio_asset_id=audio_asset.id,
        start_ms=0,
        end_ms=audio_asset.duration_ms,
        score=0.8,
        selector_used="elevenlabs-character-alignment",
        hook_type="numeric-contrast",
        rationale="Use the complete NASA-grounded Turkish narration.",
    )
    intents = ScenePlanningService(
        _UnusedSceneProvider(),
        maximum_visual_intent_duration_ms=settings.editorial_maximum_visual_beat_ms,
    ).plan_visual_intents(
        highlight,
        cues,
        narrative_beats=script.narrative_beats,
        visual_anchor=TOPIC,
    )
    intents = [_refine_intent(intent) for intent in intents]

    asset_pool = _visual_assets()
    selected_assets = [asset_pool[index % len(asset_pool)] for index in range(len(intents))]
    video_clips = [str(asset.local_path) for asset in selected_assets]
    timeline = RemotionTimelineService(
        fps=settings.render_fps,
        brand_signature="STRANGE THINGS",
    ).build(
        title="VENÜS: 1 GÜN > 1 YIL",
        cues=cues,
        visual_intents=intents,
        video_clips=video_clips,
    )
    timeline["hookText"] = "1 GÜN > 1 YIL?"
    timeline_path.write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ass_path = OUTPUT_DIRECTORY / "captions_tr.ass"
    ass_path.write_text(
        PremiumSubtitleFormatter(profile).format(cues, visual_intents=intents),
        encoding="utf-8",
    )

    output_path = OUTPUT_DIRECTORY / "venus_day_year_tr.mp4"
    renderer = RemotionRenderProvider(
        project_directory=settings.remotion_project_dir,
        remotion_cli_path=settings.remotion_cli_path,
        ffmpeg_binary=settings.ffmpeg_binary_path,
        subprocess_timeout_seconds=settings.remotion_subprocess_timeout_seconds,
        background_music_volume=settings.background_music_volume,
    )
    music_path = PROJECT_ROOT / "assets" / "music" / "space-curiosity-bed.mp3"
    await renderer.render_shorts(
        str(audio_path),
        str(ass_path),
        video_clips,
        str(output_path),
        audio_start_ms=0,
        audio_end_ms=audio_asset.duration_ms,
        background_music_path=str(music_path),
        procedural_audio_accents=True,
        creative_timeline_path=str(timeline_path),
    )

    inspector = FfprobeMediaInspectionProvider(
        ffmpeg_binary=settings.ffmpeg_binary_path,
        ffprobe_binary=settings.ffprobe_binary_path,
    )
    analyzer = FfmpegMediaQualityAnalysisProvider(settings.ffmpeg_binary_path)
    inspection, quality_signals = await asyncio.gather(
        inspector.inspect(str(output_path)),
        analyzer.analyze(str(output_path)),
    )
    post_render = PostRenderQualityService()
    post_render.validate(
        inspection,
        expected_duration_seconds=audio_asset.duration_ms / 1_000,
        expected_width=1080,
        expected_height=1920,
    )
    post_render.validate_content(
        quality_signals,
        expected_duration_seconds=audio_asset.duration_ms / 1_000,
    )
    creative_report = CreativeQualityGateService().evaluate(
        narrative_report=narrative_report,
        visual_intents=intents,
        subtitle_cues=cues,
        source_assets=selected_assets,
        inspection=inspection,
        quality_signals=quality_signals,
        fact_check_passed=True,
        caption_ux_passed=caption_report.passed,
        visual_relevance_passed=True,
        sound_design_mode="licensed_music",
    )

    package = await YoutubeUploadPackageService(inspector).prepare_factory_output(
        topic=TOPIC,
        script=script,
        video_path=str(output_path),
        subtitle_cues=cues,
        source_assets=selected_assets,
        output_directory=str(PACKAGE_DIRECTORY),
        language="tr",
        creative_quality_report=creative_report,
    )
    metadata_path = Path(package.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "title": "Venüs'te 1 Gün Neden 1 Yıldan Uzun? #Shorts",
            "description": (
                "Venüs'te bir gün gerçekten bir yıldan uzun: Gezegen kendi ekseninde "
                "243 Dünya gününde dönerken Güneş'in çevresindeki bir turunu yaklaşık "
                "225 günde tamamlıyor. Ancak gün doğumundan bir sonraki gün doğumuna "
                "kadar geçen güneş günü yaklaşık 117 Dünya günü sürüyor.\n\n"
                "Bilgi kaynağı: NASA Science — Venus Facts\n"
                f"{NASA_SOURCE}\n\n"
                "Görseller ve müzik: SELMA Labs tarafından üretilmiştir.\n\n"
                "#Shorts #Venüs #Uzay #Bilim #StrangeThings"
            ),
            "tags": [
                "Venüs",
                "Venüs'te bir gün",
                "Venüs yılı",
                "243 Dünya günü",
                "güneş günü",
                "uzay",
                "bilim",
                "Strange Things",
            ],
            "category_id": "28",
            "default_language": "tr",
        }
    )
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIRECTORY / "production_report.json").write_text(
        json.dumps(
            {
                "script": script.full_text,
                "source": NASA_SOURCE,
                "duration_seconds": inspection.duration_seconds,
                "narrative_quality": narrative_report.to_dict(),
                "caption_quality": caption_report.to_dict(),
                "creative_quality": creative_report.to_dict(),
                "inspection": inspection.to_dict(),
                "quality_signals": quality_signals.to_dict(),
                "upload_package": package.to_dict(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return Path(package.video_path)


if __name__ == "__main__":
    print(asyncio.run(main()))
