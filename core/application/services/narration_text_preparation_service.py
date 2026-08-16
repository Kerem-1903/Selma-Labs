"""Normalize narration and apply a channel-owned pronunciation lexicon."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from core.domain.entities.script import Script
from core.domain.value_objects.narration_preparation import NarrationPreparation


class NarrationTextPreparationService:
    def __init__(self, lexicon_path: str | Path | None = None) -> None:
        self._lexicon_path = Path(lexicon_path) if lexicon_path else None

    def prepare(self, script: Script) -> NarrationPreparation:
        language = self._detect_language(f"{script.topic} {script.full_text}")
        text = unicodedata.normalize("NFKC", script.full_text)
        text = text.replace("…", "...").replace("—", ", ").replace("–", "-")
        text = re.sub(r"[!?]{2,}", lambda match: match.group(0)[0], text)
        text = re.sub(r"\s+", " ", text).strip()
        replacements: list[tuple[str, str]] = []

        if language == "tr":
            text, changed = self._replace_pattern(text, r"%(\s*)(\d+(?:[.,]\d+)?)", r"yüzde \2")
            if changed:
                replacements.append(("%sayı", "yüzde sayı"))
        else:
            text, changed = self._replace_pattern(text, r"(\d+(?:[.,]\d+)?)(\s*)%", r"\1 percent")
            if changed:
                replacements.append(("number%", "number percent"))

        for source, spoken in self._lexicon(language).items():
            pattern = rf"(?<!\w){re.escape(source)}(?!\w)"
            updated, count = re.subn(pattern, spoken, text, flags=re.IGNORECASE)
            if count:
                text = updated
                replacements.append((source, spoken))
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"([,.;:!?])(?!\s|$)", r"\1 ", text)
        return NarrationPreparation(text, language, tuple(replacements))

    def _lexicon(self, language: str) -> dict[str, str]:
        built_in = {
            "tr": {"DNA": "de ne a", "RNA": "re ne a", "AI": "yapay zekâ"},
            "en": {"DNA": "D N A", "RNA": "R N A", "AI": "A I"},
        }[language]
        if self._lexicon_path is None or not self._lexicon_path.is_file():
            return built_in
        try:
            payload = json.loads(self._lexicon_path.read_text(encoding="utf-8"))
            custom = payload.get(language, {})
        except (OSError, json.JSONDecodeError, AttributeError):
            return built_in
        return {**built_in, **{str(key): str(value) for key, value in custom.items()}}

    @staticmethod
    def _replace_pattern(text: str, pattern: str, replacement: str) -> tuple[str, bool]:
        updated, count = re.subn(pattern, replacement, text)
        return updated, count > 0

    @staticmethod
    def _detect_language(text: str) -> str:
        folded = text.casefold()
        turkish_markers = sum(
            marker in folded
            for marker in ("ç", "ğ", "ı", "ö", "ş", "ü", " bir ", " ve ", " neden ")
        )
        return "tr" if turkish_markers >= 1 else "en"
