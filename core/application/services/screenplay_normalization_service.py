"""Normalize Fountain screenplay text into the shared EpisodeScript contract."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from core.domain.entities.episode_script import (
    DialogueLine,
    EpisodeScene,
    EpisodeScript,
    EpisodeScriptStatus,
    EpisodeSequence,
)
from core.domain.exceptions import PreProductionValidationError


class ScreenplayNormalizationService:
    """Keep Fountain and structured JSON on one director input boundary."""

    _HEADING = re.compile(r"^(INT\.|EXT\.|INT/EXT\.)\s+(.+)$", re.IGNORECASE)
    _SPEAKER = re.compile(
        r"^([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9 .'-]{1,48})(?:\s+\([^)]*\))?$"
    )
    _METADATA_PREFIXES = ("Title:", "Episode:", "Credit:", "Draft date:", "Language:")

    def from_fountain(
        self,
        text: str,
        *,
        script_id: str,
        title: str = "Untitled episode",
        episode_number: int = 1,
        provider_used: str = "fountain-normalizer-v1",
    ) -> EpisodeScript:
        if not text.strip():
            raise PreProductionValidationError("Fountain screenplay must not be empty.")
        scenes: list[EpisodeScene] = []
        current_heading = "UNKNOWN LOCATION"
        current_lines: list[str] = []
        current_dialogue: list[DialogueLine] = []
        current_speakers: list[str] = []
        pending_speaker: str | None = None
        title_value = title.strip() or "Untitled episode"

        for raw in text.splitlines():
            line = " ".join(raw.strip().split())
            if not line:
                pending_speaker = None
                continue
            if line.startswith(self._METADATA_PREFIXES):
                if line.startswith("Title:") and title == "Untitled episode":
                    title_value = line.split(":", 1)[1].strip() or title_value
                continue
            if line.startswith(("#", ">")):
                continue
            heading = self._HEADING.match(line)
            if heading:
                self._flush_scene(
                    scenes, script_id, current_heading, current_lines,
                    current_dialogue, current_speakers,
                )
                current_heading = heading.group(2).strip()
                current_lines, current_dialogue, current_speakers = [], [], []
                pending_speaker = None
                continue
            speaker_match = self._SPEAKER.match(line)
            if speaker_match and not line.endswith((".", "!", "?")):
                pending_speaker = speaker_match.group(1).strip().title()
                if pending_speaker not in current_speakers:
                    current_speakers.append(pending_speaker)
                continue
            if pending_speaker:
                current_dialogue.append(DialogueLine(pending_speaker, line))
                current_lines.append(f"{pending_speaker} says: {line}")
                pending_speaker = None
            else:
                current_lines.append(line)

        self._flush_scene(
            scenes, script_id, current_heading, current_lines,
            current_dialogue, current_speakers,
        )
        if not scenes:
            raise PreProductionValidationError("Fountain screenplay contains no scene headings.")
        sequence = EpisodeSequence(
            id=f"{script_id}-sequence-001",
            title=title_value,
            scenes=tuple(scenes),
        )
        return EpisodeScript(
            id=script_id,
            title=title_value,
            logline="Normalized from Fountain screenplay.",
            episode_number=episode_number,
            revision=1,
            provider_used=provider_used,
            sequences=(sequence,),
            status=EpisodeScriptStatus.DRAFT,
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _flush_scene(
        scenes: list[EpisodeScene],
        script_id: str,
        heading: str,
        lines: list[str],
        dialogue: list[DialogueLine],
        speakers: list[str],
    ) -> None:
        if not lines and not dialogue:
            return
        index = len(scenes) + 1
        scenes.append(
            EpisodeScene(
                id=f"{script_id}-scene-{index:03d}",
                title=heading,
                location=heading,
                summary=" ".join(lines).strip()[:2000] or heading,
                characters=tuple(speakers) or ("ensemble",),
                dialogue=tuple(dialogue),
            )
        )
