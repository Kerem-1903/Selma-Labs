import pytest

from core.application.services.music_director_service import MusicDirectorService
from core.domain.ports.background_music_port import BackgroundMusicPort
from core.domain.value_objects.background_track import BackgroundTrack


class FakeMusicProvider(BackgroundMusicPort):
    def __init__(self) -> None:
        self.last_theme = ""
        self.last_track_name: str | None = None

    async def select(
        self,
        theme: str,
        track_name: str | None = None,
    ) -> BackgroundTrack:
        self.last_theme = theme
        self.last_track_name = track_name
        return BackgroundTrack("track.mp3", track_name or theme, "Creator", "License", [theme])


@pytest.mark.asyncio
async def test_music_director_selects_wonder_for_flamingo_topic():
    provider = FakeMusicProvider()
    decision = await MusicDirectorService(provider).decide(
        topic="Why are flamingos pink?",
        script_text="Their color comes from food in nature.",
        scene_moods=["bright", "wonder"],
    )

    assert decision.theme == "wonder"
    assert decision.confidence >= 0.55
    assert decision.overridden is False
    assert provider.last_theme == "wonder"


@pytest.mark.asyncio
async def test_music_director_supports_theme_and_track_override():
    provider = FakeMusicProvider()
    decision = await MusicDirectorService(provider).decide(
        topic="Ocean",
        script_text="Deep sea",
        scene_moods=[],
        theme_override="energy",
        track_override="fast-track",
    )

    assert decision.theme == "energy"
    assert decision.confidence == 1.0
    assert decision.overridden is True
    assert provider.last_track_name == "fast-track"


@pytest.mark.asyncio
async def test_music_director_understands_turkish_mystery_language():
    provider = FakeMusicProvider()

    decision = await MusicDirectorService(provider).decide(
        topic="Derin okyanusun bilinmeyen canlıları",
        script_text="Karanlık denizde gizemli bir yaşam var.",
        scene_moods=["reflective"],
    )

    assert decision.theme == "mystery"
    assert decision.confidence >= 0.55
