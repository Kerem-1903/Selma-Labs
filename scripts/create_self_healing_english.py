"""Render the source-grounded English self-healing-materials review Short."""
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
from core.application.services.cue_partitioning_service import CuePartitioningService
from core.application.services.narrative_quality_service import NarrativeQualityService
from core.application.services.premium_subtitle_formatter import PremiumSubtitleFormatter
from core.application.services.remotion_timeline_service import RemotionTimelineService
from core.application.services.scene_planning_service import ScenePlanningService
from core.application.services.subtitle_formatter import SubtitleFormatter
from core.domain.entities.audio_asset import AudioAsset
from core.domain.entities.script import Script
from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.value_objects.caption_ux import CaptionSafeZoneProfile
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.word_timing import WordTiming
from infrastructure.providers.render.remotion_render_provider import RemotionRenderProvider
from infrastructure.providers.voice.elevenlabs_provider import ElevenLabsVoiceProvider


OUTPUT_DIRECTORY = PROJECT_ROOT / "output" / "self-healing-english-v3"
TITLE = "Self-Healing Materials"
BASE_SCRIPT = (
    "What if a material could seal its own wounds after being punctured? "
    "NASA researchers have studied self-healing polymers designed to respond when damage appears. "
    "In some systems, a crack releases liquid healing agents that flow into the damaged area and harden. "
    "Other polymers need heat, pressure, or time to reconnect their structure. "
    "Engineers damage samples, pull them in tensile tests, and measure how much strength returns. "
    "The goal is to stop small cracks before they spread through spacecraft, aircraft, cars, or protective equipment. "
    "The materials of the future may not just resist damage. They may repair it. "
    "Where should we use them first?"
)

SOURCES = (
    {
        "title": "NASA Technical Reports Server — Self-healing polymers",
        "url": "https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/20110023501.pdf",
    },
    {
        "title": "NASA Real World — Self-Healing Materials",
        "url": "https://nasaeclips.arc.nasa.gov/shared_assets/resources/nasas-real-world-self-healing-materials/434484main_RW7-SelfHealingMaterials_508.pdf",
    },
)


class _UnusedSceneProvider:
    provider_identity = "manual:source-grounded"

    async def plan_scenes(self, narration_text: str):  # pragma: no cover
        del narration_text
        raise RuntimeError("This production uses timed semantic visual intents only.")


def _asset_pool() -> list[Path]:
    ids = (
        "10189159",
        "8381577",
        "7169884",
        "8381584",
        "9574134",
        "8381266",
        "38822139",
        "8941171",
        "8381714",
    )
    assets = [PROJECT_ROOT / "output" / "video" / f"pexels-{asset_id}.mp4" for asset_id in ids]
    missing = [str(asset) for asset in assets if not asset.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing reviewed source clips: {missing}")
    return assets


def _refine_intent(intent):
    text = intent.narration_text.casefold()
    labels: tuple[str, ...]
    visual_job = intent.visual_job
    if "welcome to strange things" in text:
        labels = ()
        visual_job = "support_context"
    elif "what if" in text or "punctured" in text:
        labels = ("PUNCTURE", "SELF-SEAL")
        visual_job = "demonstrate_mechanism"
    elif "nasa" in text or "researchers" in text:
        labels = ("NASA RESEARCH",)
    elif "liquid healing agents" in text or "damaged area" in text:
        labels = ("CRACK", "HEALING AGENT", "HARDEN")
        visual_job = "demonstrate_mechanism"
    elif "heat, pressure" in text or "reconnect" in text:
        labels = ("HEAT", "PRESSURE", "TIME")
        visual_job = "demonstrate_mechanism"
    elif "tensile tests" in text or "strength returns" in text:
        labels = ("TENSILE TEST", "STRENGTH RETURN")
        visual_job = "compare_states"
    elif "before they spread" in text or "small cracks" in text:
        labels = ("STOP THE CRACK",)
        visual_job = "show_consequence"
    elif any(word in text for word in ("spacecraft", "aircraft", "protective equipment")):
        labels = ("SPACECRAFT", "AIRCRAFT + CARS")
        visual_job = "show_consequence"
    elif "materials of the future" in text or "repair it" in text:
        labels = ("STRONG", "SELF-REPAIRING")
        visual_job = "deliver_payoff"
    elif "where should" in text:
        labels = ("YOUR TURN",)
        visual_job = "deliver_payoff"
    else:
        labels = ()
    return replace(
        intent,
        visual_job=visual_job,
        overlay_labels=labels,
        explanatory_required=bool(labels),
        explanation_mode="hybrid" if labels else "stock",
    )


async def main() -> Path:
    settings = get_settings()
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    draft = Script.create(
        topic=TITLE,
        full_text=BASE_SCRIPT,
        target_duration_seconds=45,
        provider_used="manual:nasa-source-grounded",
    )
    enriched, report = NarrativeQualityService().validate(draft, language="en")
    script = BrandNarrationService(settings.brand_signature_text).apply(enriched)

    audio_path = OUTPUT_DIRECTORY / "narration_en.mp3"
    timeline_path = OUTPUT_DIRECTORY / "self_healing_materials_en.motion.json"
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
        cached_audio_info = MP3(audio_path).info
        duration_seconds = float(cached_audio_info.length)
        sample_rate = int(cached_audio_info.sample_rate)
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

    profile = CaptionSafeZoneProfile(
        margin_left=settings.caption_safe_margin_left,
        margin_right=settings.caption_safe_margin_right,
        caption_baseline_y=settings.caption_baseline_y,
        font_size=settings.caption_font_size,
        outline_width=settings.caption_outline_width,
        active_scale_percent=settings.caption_active_scale_percent,
        minimum_scaled_emphasis_ms=settings.caption_minimum_scaled_emphasis_ms,
    )
    caption_ux = CaptionUxService(profile)
    cues = CuePartitioningService(
        maximum_words_per_cue=settings.caption_maximum_words_per_cue,
        maximum_cue_duration_ms=settings.caption_maximum_cue_duration_ms,
        line_width_validator=caption_ux.words_fit,
    ).partition(words)
    caption_report = caption_ux.evaluate(cues)

    audio_asset = AudioAsset.create(
        source_provider=voice_provider_name,
        source_asset_id="self-healing-en-v3",
        local_path=str(audio_path),
        duration_ms=round(duration_seconds * 1_000),
        media_type="audio/mpeg",
        license="self-generated narration",
        usage_rights="publish",
        language="en",
        sample_rate_hz=sample_rate,
    )
    highlight = SelectedHighlight(
        audio_asset_id=audio_asset.id,
        start_ms=0,
        end_ms=audio_asset.duration_ms,
        score=0.72,
        selector_used="elevenlabs-character-alignment",
        hook_type="source-grounded-question",
        rationale="Use the complete verified narration with exact provider timestamps.",
    )
    intents = ScenePlanningService(
        _UnusedSceneProvider(),
        maximum_visual_intent_duration_ms=settings.editorial_maximum_visual_beat_ms,
    ).plan_visual_intents(
        highlight,
        cues,
        narrative_beats=script.narrative_beats,
        visual_anchor=TITLE,
    )
    intents = [_refine_intent(intent) for intent in intents]

    assets = _asset_pool()
    video_clips = [str(assets[index % len(assets)]) for index in range(len(intents))]
    timeline = RemotionTimelineService(
        fps=settings.render_fps,
        brand_signature="STRANGE THINGS",
    ).build(
        title=TITLE,
        cues=cues,
        visual_intents=intents,
        video_clips=video_clips,
    )
    timeline["hookText"] = "IT HEALS ITSELF?!"
    for index, scene in enumerate(timeline["scenes"]):
        scene["sourceStartFrame"] = 45 if index >= len(assets) else 0

    timeline_path.write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ass_path = OUTPUT_DIRECTORY / "captions_en.ass"
    ass_path.write_text(
        PremiumSubtitleFormatter(profile).format(cues, visual_intents=intents),
        encoding="utf-8",
    )
    subtitle_track = SubtitleTrack.create(scene_plan_id=None, cues=cues)
    srt_path = OUTPUT_DIRECTORY / "captions_en.srt"
    srt_path.write_text(SubtitleFormatter.format_srt(subtitle_track), encoding="utf-8")

    output_path = OUTPUT_DIRECTORY / "self_healing_materials_en_v3.mp4"
    renderer = RemotionRenderProvider(
        project_directory=settings.remotion_project_dir,
        remotion_cli_path=settings.remotion_cli_path,
        ffmpeg_binary=settings.ffmpeg_binary_path,
        subprocess_timeout_seconds=settings.remotion_subprocess_timeout_seconds,
        background_music_volume=settings.background_music_volume,
    )
    await renderer.render_shorts(
        str(audio_path),
        str(ass_path),
        video_clips,
        str(output_path),
        audio_start_ms=0,
        audio_end_ms=audio_asset.duration_ms,
        procedural_audio_accents=True,
        creative_timeline_path=str(timeline_path),
    )

    (OUTPUT_DIRECTORY / "script_en.txt").write_text(script.full_text, encoding="utf-8")
    (OUTPUT_DIRECTORY / "production_metadata.json").write_text(
        json.dumps(
            {
                "title": "This Material Can Heal Itself After Damage",
                "language": "en",
                "brand_signature": settings.brand_signature_text,
                "duration_seconds": duration_seconds,
                "narrative_quality": report.to_dict(),
                "caption_quality": caption_report.to_dict(),
                "sources": SOURCES,
                "cta": timeline["ctaText"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path


if __name__ == "__main__":
    print(asyncio.run(main()))
