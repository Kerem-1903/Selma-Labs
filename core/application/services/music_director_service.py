from __future__ import annotations

from core.domain.ports.background_music_port import BackgroundMusicPort
from core.domain.value_objects.music_selection_decision import MusicSelectionDecision


THEME_KEYWORDS = {
    "mystery": {
        "deep",
        "ocean",
        "space",
        "unknown",
        "secret",
        "night",
        "dark",
        "ancient",
        "mystery",
        "derin",
        "okyanus",
        "uzay",
        "bilinmeyen",
        "gizem",
        "gece",
        "karanlık",
        "antik",
        "sır",
    },
    "wonder": {
        "animal",
        "nature",
        "color",
        "light",
        "life",
        "flamingo",
        "kangaroo",
        "beautiful",
        "surprising",
        "hayvan",
        "doğa",
        "renk",
        "ışık",
        "yaşam",
        "güzel",
        "şaşırtıcı",
    },
    "energy": {
        "physics",
        "speed",
        "power",
        "technology",
        "experiment",
        "electric",
        "explosion",
        "fast",
        "fizik",
        "hız",
        "güç",
        "teknoloji",
        "deney",
        "elektrik",
        "patlama",
    },
}


class MusicDirectorService:
    def __init__(
        self,
        provider: BackgroundMusicPort,
        confidence_threshold: float = 0.55,
    ) -> None:
        self._provider = provider
        self._confidence_threshold = confidence_threshold

    async def decide(
        self,
        *,
        topic: str,
        script_text: str,
        scene_moods: list[str],
        theme_override: str | None = None,
        track_override: str | None = None,
    ) -> MusicSelectionDecision:
        if theme_override:
            theme = theme_override.casefold()
            confidence = 1.0
            rationale = "Theme selected by explicit CLI override."
            overridden = True
        else:
            corpus = " ".join([topic, script_text, *scene_moods]).casefold()
            scores = {
                theme: sum(1 for keyword in keywords if keyword in corpus)
                for theme, keywords in THEME_KEYWORDS.items()
            }
            theme, best_score = max(scores.items(), key=lambda item: item[1])
            total_score = sum(scores.values())
            confidence = best_score / total_score if total_score else 0.0
            if confidence < self._confidence_threshold:
                theme = "wonder"
                rationale = (
                    "Mood confidence was below threshold; used safe Wonder fallback."
                )
            else:
                rationale = f"Selected from topic, verified script, and scene moods: {scores}."
            overridden = False

        track = await self._provider.select(theme, track_name=track_override)
        if track_override:
            overridden = True
            rationale += " Track selected by explicit CLI override."
        return MusicSelectionDecision(
            theme=theme,
            confidence=round(confidence, 4),
            rationale=rationale,
            track=track,
            overridden=overridden,
        )
