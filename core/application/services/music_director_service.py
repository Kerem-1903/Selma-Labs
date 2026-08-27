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

    async def decide_chapters(self, timeline_duration: float, scene_moods: list[str]) -> list[dict]:
        """
        Advanced Music Director logic.
        Splits the timeline into chapters based on mood changes and requests tracks.
        """
        chapters = []
        if not scene_moods:
            track = await self._provider.select("wonder")
            chapters.append({
                "file_path": track.file_path,
                "start_time": 0.0,
                "end_time": timeline_duration,
                "volume": 0.3
            })
            return chapters

        if timeline_duration < 30:
            mood = scene_moods[0] if scene_moods else "wonder"
            track = await self._provider.select(mood)
            chapters.append({
                "file_path": track.file_path,
                "start_time": 0.0,
                "end_time": timeline_duration,
                "volume": 0.3
            })
        else:
            mid_point = timeline_duration / 2.0
            mood1 = scene_moods[0]
            mood2 = scene_moods[-1] if len(scene_moods) > 1 else mood1

            track1 = await self._provider.select(mood1)
            chapters.append({
                "file_path": track1.file_path,
                "start_time": 0.0,
                "end_time": mid_point + 2.0,
                "volume": 0.3
            })

            track2 = await self._provider.select(mood2)
            chapters.append({
                "file_path": track2.file_path,
                "start_time": mid_point,
                "end_time": timeline_duration,
                "volume": 0.3
            })

        return chapters
