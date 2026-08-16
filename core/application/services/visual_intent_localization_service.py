"""Localize stock-search concepts without changing narration or subtitles."""
from __future__ import annotations

from collections.abc import Sequence
import re

from core.domain.ports.translation_port import TranslationPort
from core.domain.value_objects.visual_intent import VisualIntent


class VisualIntentLocalizationService:
    """Translate editorial keywords to the stock catalog's search language."""

    def __init__(self, translation_provider: TranslationPort) -> None:
        self._translation_provider = translation_provider

    async def localize(
        self,
        intents: Sequence[VisualIntent],
        target_language: str = "English",
        source_anchor: str | None = None,
    ) -> list[VisualIntent]:
        if not intents:
            return []
        terms = list(
            dict.fromkeys(
                term
                for intent in intents
                for term in (
                    intent.primary_keyword,
                    *intent.secondary_keywords,
                    *intent.required_subjects,
                    *intent.required_actions,
                    *intent.required_relations,
                )
                if term.strip()
            )
        )
        requested_terms = [*terms, *([source_anchor.strip()] if source_anchor and source_anchor.strip() else [])]
        translations = await self._translation_provider.translate_texts(
            requested_terms, target_language
        )
        if len(translations) != len(requested_terms):
            raise ValueError("Visual keyword translation count does not match input.")
        localized = {
            source: translated.strip()
            for source, translated in zip(requested_terms, translations)
            if translated.strip()
        }
        if len(localized) != len(requested_terms):
            raise ValueError("Visual keyword translation returned an empty term.")
        subject_keywords = [
            keyword
            for intent in intents
            for term in intent.required_subjects
            for keyword in self._search_keywords(localized[term])
        ]
        topic_keywords = (
            self._search_keywords(localized[source_anchor.strip()])
            if source_anchor and source_anchor.strip()
            else []
        )
        # Required subjects are a stronger stock-search anchor than adjectives
        # from a translated question (for example "longer" in a Venus topic).
        anchor_keywords = list(
            dict.fromkeys([*subject_keywords, *topic_keywords])
        )[:3]
        return [
            VisualIntent(
                primary_keyword=(
                    anchor_keywords[0]
                    if anchor_keywords
                    else localized[intent.primary_keyword]
                ),
                secondary_keywords=self._secondary_keywords(
                    intent, localized, anchor_keywords
                ),
                mood=intent.mood,
                motion_type=intent.motion_type,
                forbidden_concepts=intent.forbidden_concepts,
                start_ms=intent.start_ms,
                end_ms=intent.end_ms,
                narrative_role=intent.narrative_role,
                shot_type=intent.shot_type,
                narration_text=intent.narration_text,
                visual_job=intent.visual_job,
                required_subjects=tuple(
                    localized[term] for term in intent.required_subjects
                ),
                required_actions=tuple(
                    localized[term] for term in intent.required_actions
                ),
                required_relations=tuple(
                    localized[term] for term in intent.required_relations
                ),
                forbidden_dominant_subjects=intent.forbidden_dominant_subjects,
                explanation_mode=intent.explanation_mode,
                overlay_labels=intent.overlay_labels,
                explanatory_required=intent.explanatory_required,
            )
            for intent in intents
        ]

    @classmethod
    def _secondary_keywords(
        cls,
        intent: VisualIntent,
        localized: dict[str, str],
        anchor_keywords: list[str],
    ) -> tuple[str, ...]:
        candidates: list[str] = []
        current = cls._search_keywords(localized[intent.primary_keyword])
        if current and (not anchor_keywords or current[0] != anchor_keywords[0]):
            candidates.append(current[0])
        candidates.extend(anchor_keywords[1:])
        return tuple(dict.fromkeys(candidates))[:2]

    @staticmethod
    def _search_keywords(text: str) -> list[str]:
        stop_words = {
            "a", "an", "and", "are", "do", "does", "have", "has", "how",
            "in", "is", "it", "of", "than", "the", "their", "they", "to", "why",
            "with", "one", "two", "three", "four", "five",
        }
        tokens = re.findall(r"[a-zA-Z']+", text.lower())
        meaningful = list(
            dict.fromkeys(token for token in tokens if token not in stop_words and len(token) > 2)
        )
        return sorted(meaningful, key=lambda token: (-len(token), meaningful.index(token)))[:3]
