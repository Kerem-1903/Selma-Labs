import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.provider_registry import get_translation_provider
from config.settings import get_settings
from core.application.services.subtitle_translation_service import SubtitleTranslationService
from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.value_objects.subtitle_cue import SubtitleCue
from infrastructure.storage.local_fs_storage import LocalFsStorage

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate a subtitle track into multiple languages.")
    parser.add_argument("--track-id", required=True, help="Dummy ID for testing source track")
    parser.add_argument("--target-languages", nargs="+", required=True, help="Target languages to translate to")
    return parser


async def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    sample_cues = [
        SubtitleCue(index=1, scene_index=0, start_time=0.0, end_time=4.0, text="This is a test."),
        SubtitleCue(index=2, scene_index=0, start_time=4.0, end_time=8.0, text="Welcome to SELMA Labs."),
    ]
    source_track = SubtitleTrack(
        id=args.track_id,
        scene_plan_id="dummy_scene_plan",
        cues=sample_cues,
        total_duration_seconds=8.0,
    )

    settings = get_settings()
    provider = get_translation_provider(settings)
    storage = LocalFsStorage(root_dir=".")
    service = SubtitleTranslationService(translation_provider=provider, storage=storage)

    logger.info(f"Translating track {args.track_id} to {args.target_languages}")
    translated_tracks = await service.translate_multiple(source_track, args.target_languages)

    for track in translated_tracks:
        logger.info(f"Finished {track.target_language}, exporting...")
        refs = await service.export(track, f"output/translation/{track.id}")
        logger.info(f"Saved {track.target_language}: SRT -> {refs['srt'].path}")
        logger.info(f"Saved {track.target_language}: VTT -> {refs['vtt'].path}")


if __name__ == "__main__":
    asyncio.run(main())
