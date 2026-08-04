import logging
from typing import Any

from core.application.services.subtitle_formatter import SubtitleFormatter
from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.entities.translated_subtitle_track import TranslatedSubtitleTrack
from core.domain.exceptions import SubtitleTranslationError
from core.domain.ports.storage_port import StoragePort
from core.domain.ports.translation_port import TranslationPort
from core.domain.value_objects.subtitle_cue import SubtitleCue

logger = logging.getLogger(__name__)


class SubtitleTranslationService:
    """
    Service responsible for translating SubtitleTrack instances while preserving
    cue timestamps, counts, and ordering.
    """

    def __init__(
        self,
        translation_provider: TranslationPort,
        storage: StoragePort | None = None,
    ) -> None:
        self._provider = translation_provider
        self._storage = storage

    async def translate(
        self,
        source_track: SubtitleTrack,
        target_language: str,
    ) -> TranslatedSubtitleTrack:
        if not source_track.cues:
            raise SubtitleTranslationError("Cannot translate a SubtitleTrack with no cues.")

        clean_target = target_language.strip().lower()
        if not clean_target:
            raise SubtitleTranslationError("Target language cannot be empty.")

        source_texts = [cue.text for cue in source_track.cues]
        logger.info(
            f"Translating {len(source_texts)} cues for track {source_track.id} into '{clean_target}'"
        )

        translated_texts = await self._provider.translate_texts(source_texts, clean_target)

        if len(translated_texts) != len(source_track.cues):
            raise SubtitleTranslationError(
                f"Cue count mismatch after translation: expected {len(source_track.cues)}, "
                f"got {len(translated_texts)}"
            )

        translated_cues = [
            SubtitleCue(
                index=cue.index,
                scene_index=cue.scene_index,
                start_time=cue.start_time,
                end_time=cue.end_time,
                text=trans_text,
            )
            for cue, trans_text in zip(source_track.cues, translated_texts)
        ]

        return TranslatedSubtitleTrack.create(
            source_subtitle_track_id=source_track.id,
            target_language=clean_target,
            cues=translated_cues,
            total_duration_seconds=source_track.total_duration_seconds,
        )

    async def translate_multiple(
        self,
        source_track: SubtitleTrack,
        target_languages: list[str],
    ) -> list[TranslatedSubtitleTrack]:
        if not target_languages:
            raise SubtitleTranslationError("Target languages list cannot be empty.")

        cleaned_langs = [lang.strip().lower() for lang in target_languages]
        if any(not lang for lang in cleaned_langs):
            raise SubtitleTranslationError("Target languages cannot contain empty strings.")

        if len(cleaned_langs) != len(set(cleaned_langs)):
            raise SubtitleTranslationError("Duplicate target languages are not allowed.")

        results: list[TranslatedSubtitleTrack] = []
        for lang in cleaned_langs:
            track = await self.translate(source_track, lang)
            results.append(track)
            
        return results

    async def export(self, track: TranslatedSubtitleTrack, base_key: str) -> dict[str, Any]:
        if not self._storage:
            raise SubtitleTranslationError("StoragePort is required to export subtitles.")

        temp_track = SubtitleTrack(
            id=track.id,
            scene_plan_id=track.source_subtitle_track_id,
            cues=track.cues,
            total_duration_seconds=track.total_duration_seconds,
            created_at=track.created_at
        )

        srt_content = SubtitleFormatter.format_srt(temp_track)
        vtt_content = SubtitleFormatter.format_vtt(temp_track)

        srt_key = f"{base_key}_{track.target_language}.srt"
        vtt_key = f"{base_key}_{track.target_language}.vtt"

        srt_ref = await self._storage.save(srt_key, srt_content.encode("utf-8"), "text/plain")
        vtt_ref = await self._storage.save(vtt_key, vtt_content.encode("utf-8"), "text/vtt")

        return {"srt": srt_ref, "vtt": vtt_ref}
