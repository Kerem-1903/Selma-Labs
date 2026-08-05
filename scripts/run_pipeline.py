#!/usr/bin/env python3
"""
Operational Pipeline CLI — End-to-End Execution for SELMA Labs (Sprints 1–17).

Connects existing Sprint 1–17 domain capabilities into a single local workflow:
  1. Script Generation (Claude / Fake)
  2. Voice Narration Generation (ElevenLabs / Fake)
  3. Scene Planning & Timing Allocation (Claude / Fake)
  4. Visual Asset Search & Download (Pexels / Fake)
  5. Asset Matching & Selection Ranking
  6. Timeline Creation
  7. Vertical Video Rendering (FFmpeg / Fake)
  8. Subtitle Generation & Formatting (SRT / WebVTT)
  9. Subtitle Translation (Optional, Claude / Fake)
 10. Organized Output Storage & Metadata Summary

Usage:
  # Live mode (requires API credentials in .env):
  python scripts/run_pipeline.py "The mystery of the Mariana Trench" --output output/mariana-trench

  # Offline dry-run mode (runs 100% offline using mock adapters):
  python scripts/run_pipeline.py "The mystery of the Mariana Trench" --dry-run --output output/mariana-trench-dry
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.provider_registry import (
    get_render_provider,
    get_scene_planning_provider,
    get_translation_provider,
    get_video_source_provider,
    get_voice_provider,
)
from config.settings import get_settings
from core.application.services.render_service import RenderService
from core.application.services.scene_asset_matching_service import (
    DEFAULT_CANDIDATES_PER_SCENE,
    SceneAssetMatchingService,
)
from core.application.services.scene_planning_service import ScenePlanningService
from core.application.services.script_service import ScriptService
from core.application.services.subtitle_service import SubtitleService
from core.application.services.subtitle_translation_service import SubtitleTranslationService
from core.application.services.timeline_service import TimelineService
from core.application.services.video_search_service import VideoSearchService
from core.application.services.voice_service import VoiceService
from core.domain.entities.media_asset import MediaAsset
from core.domain.entities.rendered_video import RenderedVideo
from core.domain.entities.script import Script
from core.domain.exceptions import SelmaError
from core.domain.ports.render_port import RenderPort
from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.ports.script_generator_port import ScriptGeneratorPort
from core.domain.ports.translation_port import TranslationPort
from core.domain.ports.video_source_port import VideoSourcePort
from core.domain.ports.voice_generator_port import VoiceGeneratorPort
from core.domain.value_objects.generated_audio import GeneratedAudio
from core.domain.value_objects.render_result import RenderResult
from core.domain.value_objects.scene import Scene
from infrastructure.providers.script.claude_script_provider import ClaudeScriptProvider
from infrastructure.storage.local_fs_storage import LocalFsStorage


# -----------------------------------------------------------------------------
# Offline Fake / Mock Adapters for Dry-Run Mode
# -----------------------------------------------------------------------------

class DryRunScriptGenerator(ScriptGeneratorPort):
    @property
    def provider_identity(self) -> str:
        return "dry_run:script"

    async def generate_script(self, topic: str, target_duration_seconds: int) -> Script:
        narration = (
            f"Exploring {topic}. The ocean floor conceals ancient geological mysteries, "
            "dramatic trench formations, extreme pressure ecosystems, and unexplored deep "
            "water abysses that challenge modern oceanographic science. Scientists utilize "
            "advanced submersible vehicles and robotic probes to map the Mariana Trench, "
            "discovering unique biological adaptations and hydrothermal vent systems. "
            "These findings expand our understanding of planetary oceanography, marine biology, "
            "and the fundamental origin of extremophile life on planet Earth."
        )
        return Script.create(
            topic=topic,
            full_text=narration,
            target_duration_seconds=target_duration_seconds,
            provider_used=self.provider_identity,
        )


class DryRunVoiceGenerator(VoiceGeneratorPort):
    @property
    def provider_identity(self) -> str:
        return "dry_run:voice"

    async def generate_voice(self, text: str, voice_name: str) -> GeneratedAudio:
        # 1-second dummy MP3 header bytes
        dummy_mp3 = (
            b"\xff\xfb\x90\xc4\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"DRY_RUN_AUDIO_DATA_FOR_PIPELINE_VALIDATION_PURPOSES_ONLY_MP3"
        )
        return GeneratedAudio(
            audio_bytes=dummy_mp3,
            duration_seconds=15.0,
            sample_rate=44100,
            provider=self.provider_identity,
            voice_name=voice_name,
        )


class DryRunScenePlanner(ScenePlanningPort):
    @property
    def provider_identity(self) -> str:
        return "dry_run:scene_planner"

    async def plan_scenes(self, narration_text: str) -> list[Scene]:
        return [
            Scene(
                index=0,
                narration="Exploring the ocean floor and ancient underwater mysteries.",
                search_keywords=["ocean", "underwater"],
                detected_objects=["water", "submersible"],
                location="deep sea",
                mood="mysterious",
                visual_priority="high",
            ),
            Scene(
                index=1,
                narration="Extreme pressure ecosystems and unexplored deep water abysses.",
                search_keywords=["abyss", "marine life"],
                detected_objects=["fish", "coral"],
                location="trench",
                mood="dramatic",
                visual_priority="medium",
            ),
        ]


class DryRunVideoSource(VideoSourcePort):
    @property
    def provider_identity(self) -> str:
        return "dry_run:video_source"

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        return [
            MediaAsset(
                id=f"dry-asset-{hash(query) & 0xffff}",
                provider=self.provider_identity,
                provider_asset_id=f"pexels-{hash(query) & 0xffff}",
                media_type="video",
                original_url="https://example.com/dry_run_video.mp4",
                thumbnail_url="https://example.com/dry_run_thumb.jpg",
                width=1080,
                height=1920,
                duration_seconds=10.0,
                fps=30.0,
                tags=[query],
                attribution="Pexels Dry Run Creator",
                license="CC0",
            )
        ]

    async def download(self, asset: MediaAsset) -> bytes:
        return b"DRY_RUN_MP4_VIDEO_BYTES_DATA"


class DryRunRenderProvider(RenderPort):
    @property
    def provider_identity(self) -> str:
        return "dry_run:render_ffmpeg"

    async def render(self, timeline: Any, narration_audio_path: str) -> RenderResult:
        dummy_mp4_path = Path(narration_audio_path).parent / f"dry_run_{timeline.id}.mp4"
        dummy_mp4_path.write_bytes(b"DRY_RUN_RENDERED_MP4_VIDEO_BYTES")
        return RenderResult(
            output_path=str(dummy_mp4_path),
            duration_seconds=timeline.total_duration_seconds,
            width=1080,
            height=1920,
            fps=30.0,
        )


class DryRunTranslationProvider(TranslationPort):
    @property
    def provider_identity(self) -> str:
        return "dry_run:translation"

    async def translate_texts(self, texts: List[str], target_language: str) -> List[str]:
        return [f"[{target_language.upper()}] {t}" for t in texts]


# -----------------------------------------------------------------------------
# Argument Parsing
# -----------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run end-to-end SELMA Shorts video generation pipeline."
    )
    parser.add_argument(
        "topic",
        nargs="?",
        type=str,
        default=None,
        help="Topic for the SELMA Short (e.g. 'The mystery of the Mariana Trench').",
    )
    parser.add_argument(
        "--topic",
        dest="topic_option",
        type=str,
        default=None,
        help="Alternative flag to specify topic.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output directory path for run artifacts (defaults to output/run-<uuid>).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Target spoken duration in seconds (15-90). Defaults to settings value.",
    )
    parser.add_argument(
        "--voice-id",
        type=str,
        default=None,
        help="Override configured ElevenLabs voice ID.",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        help="Primary subtitle language (default: en).",
    )
    parser.add_argument(
        "--target-languages",
        nargs="+",
        default=[],
        help="Additional target languages for subtitle translation (e.g. --target-languages es fr de).",
    )
    parser.add_argument(
        "--candidates-per-scene",
        type=int,
        default=DEFAULT_CANDIDATES_PER_SCENE,
        help=f"Maximum asset candidates to evaluate per scene (default: {DEFAULT_CANDIDATES_PER_SCENE}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute fully offline using mock adapters without live API keys or network requests.",
    )
    return parser


# -----------------------------------------------------------------------------
# Pipeline Orchestrator Composition Root
# -----------------------------------------------------------------------------

def _relative_path(absolute_path: str, run_dir: Path) -> str:
    """Convert an absolute storage path to a run-directory-relative path.

    Falls back to the original path if it is not under run_dir (should not
    happen in normal operation, but avoids crashing on edge cases).
    """
    try:
        return str(Path(absolute_path).relative_to(run_dir))
    except ValueError:
        return absolute_path


async def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    topic = args.topic or args.topic_option
    if not topic or not topic.strip():
        parser.error("A topic must be specified as a positional argument or via --topic.")

    if args.duration is not None and not (15 <= args.duration <= 90):
        parser.error("--duration must be between 15 and 90 seconds.")

    run_id = str(uuid.uuid4())[:8]
    sanitized_topic = "".join(c if c.isalnum() else "_" for c in topic.strip().lower())[:30]
    
    if args.output:
        run_dir = Path(args.output).resolve()
    else:
        run_dir = (Path("output") / f"{sanitized_topic}_{run_id}").resolve()

    # Create subdirectories
    script_dir = run_dir / "script"
    audio_dir = run_dir / "audio"
    scenes_dir = run_dir / "scenes"
    assets_dir = run_dir / "assets"
    timeline_dir = run_dir / "timeline"
    subtitles_dir = run_dir / "subtitles"
    video_dir = run_dir / "video"

    for d in [run_dir, script_dir, audio_dir, scenes_dir, assets_dir, timeline_dir, subtitles_dir, video_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Logging setup
    log_file = run_dir / "run.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger = logging.getLogger("run_pipeline")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    logger.info("==================================================")
    logger.info(f"Starting SELMA Labs Pipeline Run: {run_id}")
    logger.info(f"Topic: '{topic}' | Mode: {'DRY-RUN (Offline)' if args.dry_run else 'LIVE'}")
    logger.info(f"Run Directory: {run_dir}")
    logger.info("==================================================")

    is_simulated = args.dry_run

    metadata: dict[str, Any] = {
        "run_id": run_id,
        "topic": topic,
        "mode": "dry_run" if args.dry_run else "live",
        "simulated": is_simulated,
        "status": "RUNNING",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_directory": str(run_dir),
        "stages": {},
        "artifacts": {},
    }

    try:
        storage = LocalFsStorage(root_dir=str(run_dir))
        settings = get_settings()
        target_duration = args.duration or settings.default_target_duration_seconds

        # Stage 1: Script Generation
        logger.info("[1/8] Generating Script...")
        if args.dry_run:
            script_provider = DryRunScriptGenerator()
        else:
            script_provider = ClaudeScriptProvider(
                api_key=settings.anthropic_api_key, model=settings.script_model
            )
        script_service = ScriptService(script_provider)
        script = await script_service.generate(topic, target_duration)
        
        script_json_path = script_dir / "script.json"
        script_txt_path = script_dir / "script.txt"
        script_dict = {
            "id": script.id,
            "topic": script.topic,
            "full_text": script.full_text,
            "target_duration_seconds": script.target_duration_seconds,
            "estimated_word_count": script.estimated_word_count,
            "provider_used": script.provider_used,
            "created_at": script.created_at.isoformat() if hasattr(script.created_at, "isoformat") else str(script.created_at),
        }
        script_json_path.write_text(json.dumps(script_dict, indent=2), encoding="utf-8")
        script_txt_path.write_text(script.full_text, encoding="utf-8")
        
        metadata["stages"]["script"] = {
            "status": "COMPLETED",
            "script_id": script.id,
            "word_count": script.estimated_word_count,
            "provider": script.provider_used,
        }
        metadata["artifacts"]["script_json"] = str(script_json_path.relative_to(run_dir))
        metadata["artifacts"]["script_txt"] = str(script_txt_path.relative_to(run_dir))
        logger.info(f"      OK: Script ID {script.id} ({script.estimated_word_count} words)")

        # Stage 2: Voice Generation
        logger.info("[2/8] Generating Voice Narration...")
        if args.dry_run:
            voice_provider = DryRunVoiceGenerator()
        else:
            voice_provider = get_voice_provider(settings)
        voice_service = VoiceService(
            provider=voice_provider,
            storage=storage,
            default_voice_name=args.voice_id or settings.elevenlabs_voice_id,
        )
        voice_track = await voice_service.generate(script)

        voice_rel_path = _relative_path(voice_track.file_path, run_dir)
        metadata["stages"]["voice"] = {
            "status": "COMPLETED",
            "simulated": is_simulated,
            "audio_id": voice_track.audio_id,
            "duration_seconds": voice_track.duration_seconds,
            "provider": voice_track.provider,
            "file_path": voice_rel_path,
        }
        metadata["artifacts"]["narration_audio"] = voice_rel_path
        logger.info(f"      OK: Voice Track ID {voice_track.audio_id} ({voice_track.duration_seconds:.1f}s)")

        # Stage 3: Scene Planning
        logger.info("[3/8] Planning Scenes...")
        if args.dry_run:
            scene_provider = DryRunScenePlanner()
        else:
            scene_provider = get_scene_planning_provider(settings)
        scene_service = ScenePlanningService(scene_provider)
        scene_plan = await scene_service.plan(script, voice_track)

        scene_plan_json_path = scenes_dir / "scene_plan.json"
        scene_plan_json_path.write_text(json.dumps(scene_plan.to_dict(), indent=2), encoding="utf-8")
        
        metadata["stages"]["scene_planning"] = {
            "status": "COMPLETED",
            "scene_plan_id": scene_plan.id,
            "scene_count": len(scene_plan.scenes),
            "provider": scene_plan.provider_used,
        }
        metadata["artifacts"]["scene_plan_json"] = str(scene_plan_json_path.relative_to(run_dir))
        logger.info(f"      OK: Scene Plan ID {scene_plan.id} ({len(scene_plan.scenes)} scenes)")

        # Stage 4 & 5: Visual Asset Search & Asset Matching
        logger.info("[4/8] Searching & Matching Visual Assets...")
        if args.dry_run:
            video_provider = DryRunVideoSource()
        else:
            video_provider = get_video_source_provider(settings)
        video_search_service = VideoSearchService(video_provider, storage)
        matching_service = SceneAssetMatchingService(
            video_search_service, candidates_per_scene=args.candidates_per_scene
        )
        asset_match_plan = await matching_service.match(scene_plan)

        asset_match_json_path = assets_dir / "asset_match_plan.json"
        asset_match_json_path.write_text(json.dumps(asset_match_plan.to_dict(), indent=2), encoding="utf-8")

        metadata["stages"]["asset_matching"] = {
            "status": "COMPLETED",
            "asset_match_plan_id": asset_match_plan.id,
            "matched_scenes": len(asset_match_plan.matches),
        }
        metadata["artifacts"]["asset_match_plan_json"] = str(asset_match_json_path.relative_to(run_dir))
        logger.info(f"      OK: Asset Match Plan ID {asset_match_plan.id}")

        # Stage 6: Timeline Assembly
        logger.info("[5/8] Building Timeline...")
        timeline_service = TimelineService(video_search_service)
        timeline = await timeline_service.create(asset_match_plan)

        timeline_json_path = timeline_dir / "timeline.json"
        timeline_json_path.write_text(json.dumps(timeline.to_dict(), indent=2), encoding="utf-8")

        metadata["stages"]["timeline"] = {
            "status": "COMPLETED",
            "timeline_id": timeline.id,
            "clip_count": len(timeline.clips),
            "total_duration_seconds": timeline.total_duration_seconds,
        }
        metadata["artifacts"]["timeline_json"] = str(timeline_json_path.relative_to(run_dir))
        logger.info(f"      OK: Timeline ID {timeline.id} ({len(timeline.clips)} clips)")

        # Stage 7: Video Rendering
        logger.info("[6/8] Rendering Video...")
        if args.dry_run:
            render_port = DryRunRenderProvider()
        else:
            render_port = get_render_provider(settings)
        render_service = RenderService(render_port=render_port, storage=storage)
        rendered_video = await render_service.render(timeline, voice_track.file_path)

        video_rel_path = _relative_path(rendered_video.video_path, run_dir)
        metadata["stages"]["rendering"] = {
            "status": "COMPLETED",
            "simulated": is_simulated,
            "rendered_video_id": rendered_video.id,
            "video_path": video_rel_path,
            "duration_seconds": rendered_video.duration_seconds,
            "resolution": f"{rendered_video.width}x{rendered_video.height}",
        }
        metadata["artifacts"]["video_mp4"] = video_rel_path
        logger.info(f"      OK: Rendered Video ID {rendered_video.id}")

        # Stage 8: Subtitle Generation & Formatting
        logger.info("[7/8] Generating Subtitles...")
        subtitle_service = SubtitleService(storage=storage)
        subtitle_track = subtitle_service.generate(scene_plan)
        subtitle_refs = await subtitle_service.export(
            subtitle_track, base_key=f"subtitles/subtitles_{args.language}"
        )

        srt_rel = _relative_path(subtitle_refs["srt"].path, run_dir)
        vtt_rel = _relative_path(subtitle_refs["vtt"].path, run_dir)
        metadata["stages"]["subtitles"] = {
            "status": "COMPLETED",
            "subtitle_track_id": subtitle_track.id,
            "cue_count": len(subtitle_track.cues),
            "primary_language": args.language,
            "srt_path": srt_rel,
            "vtt_path": vtt_rel,
        }
        metadata["artifacts"][f"subtitles_{args.language}_srt"] = srt_rel
        metadata["artifacts"][f"subtitles_{args.language}_vtt"] = vtt_rel
        logger.info(f"      OK: Subtitle Track ID {subtitle_track.id} ({len(subtitle_track.cues)} cues)")

        # Stage 9: Subtitle Translation (Optional)
        if args.target_languages:
            logger.info(f"[8/8] Translating Subtitles to {args.target_languages}...")
            if args.dry_run:
                translation_provider = DryRunTranslationProvider()
            else:
                translation_provider = get_translation_provider(settings)
            translation_service = SubtitleTranslationService(
                translation_provider=translation_provider, storage=storage
            )
            translated_tracks = await translation_service.translate_multiple(
                subtitle_track, args.target_languages
            )
            translated_info = {}
            for t_track in translated_tracks:
                t_refs = await translation_service.export(
                    t_track, base_key=f"subtitles/subtitles_{t_track.target_language}"
                )
                t_srt_rel = _relative_path(t_refs["srt"].path, run_dir)
                t_vtt_rel = _relative_path(t_refs["vtt"].path, run_dir)
                translated_info[t_track.target_language] = {
                    "srt": t_srt_rel,
                    "vtt": t_vtt_rel,
                }
                metadata["artifacts"][f"subtitles_{t_track.target_language}_srt"] = t_srt_rel
                metadata["artifacts"][f"subtitles_{t_track.target_language}_vtt"] = t_vtt_rel
            metadata["stages"]["translation"] = {
                "status": "COMPLETED",
                "translated_languages": args.target_languages,
                "details": translated_info,
            }
            logger.info("      OK: Subtitle translation complete.")
        else:
            logger.info("[8/8] Subtitle translation skipped (no --target-languages specified).")

        metadata["status"] = "SUCCESS"
        metadata["completed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info("==================================================")
        logger.info("Pipeline Execution Successfully Finished!")
        logger.info(f"Output Directory: {run_dir}")
        logger.info("==================================================")

    except SelmaError as exc:
        metadata["status"] = "FAILED"
        metadata["error_message"] = str(exc)
        metadata["failed_at"] = datetime.now(timezone.utc).isoformat()
        logger.error(f"Pipeline Execution Failed: {exc}", exc_info=True)
        sys.exit(1)
    except Exception as exc:
        metadata["status"] = "FAILED"
        metadata["error_message"] = f"Unexpected error: {exc}"
        metadata["failed_at"] = datetime.now(timezone.utc).isoformat()
        logger.error(f"Pipeline Execution Encountered Error: {exc}", exc_info=True)
        sys.exit(1)
    finally:
        metadata_file = run_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        file_handler.close()
        logger.removeHandler(file_handler)
        logger.removeHandler(stream_handler)


if __name__ == "__main__":
    asyncio.run(main())
