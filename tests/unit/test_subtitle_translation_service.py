import pytest
from typing import List

from core.application.services.subtitle_translation_service import SubtitleTranslationService
from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.exceptions import SubtitleTranslationError
from core.domain.ports.translation_port import TranslationPort
from core.domain.value_objects.subtitle_cue import SubtitleCue


class FakeTranslationPort(TranslationPort):
    def __init__(self, simulate_mismatch: bool = False):
        self.simulate_mismatch = simulate_mismatch

    @property
    def provider_identity(self) -> str:
        return "fake:translation"

    async def translate_texts(self, texts: List[str], target_language: str) -> List[str]:
        if self.simulate_mismatch:
            return ["mismatched length array"]
        return [f"[{target_language}] {t}" for t in texts]


@pytest.mark.asyncio
async def test_translate_success():
    fake_port = FakeTranslationPort()
    service = SubtitleTranslationService(translation_provider=fake_port)

    cues = [
        SubtitleCue(index=1, scene_index=0, start_time=0.0, end_time=2.0, text="Hello"),
        SubtitleCue(index=2, scene_index=0, start_time=2.0, end_time=4.0, text="World"),
    ]
    source = SubtitleTrack(id="sub-1", scene_plan_id="plan-1", cues=cues, total_duration_seconds=4.0)

    result = await service.translate(source, "es")

    assert result.target_language == "es"
    assert result.source_subtitle_track_id == "sub-1"
    assert len(result.cues) == 2
    assert result.cues[0].text == "[es] Hello"
    assert result.cues[0].start_time == 0.0


@pytest.mark.asyncio
async def test_translate_multiple_rejects_duplicates():
    fake_port = FakeTranslationPort()
    service = SubtitleTranslationService(translation_provider=fake_port)
    source = SubtitleTrack(id="sub-1", scene_plan_id="plan-1", cues=[], total_duration_seconds=0.0)

    with pytest.raises(SubtitleTranslationError, match="Duplicate"):
        await service.translate_multiple(source, ["fr", "fr"])


@pytest.mark.asyncio
async def test_translate_raises_on_cue_mismatch():
    """Verify that SubtitleTranslationService enforces cue count preservation between
    source track and provider response, raising SubtitleTranslationError on mismatch.

    FakeTranslationPort(simulate_mismatch=True) returns a 1-element list. Thus, the
    source track fixture must have >= 2 cues so len(source.cues) != len(translated_texts).
    """
    fake_port = FakeTranslationPort(simulate_mismatch=True)
    service = SubtitleTranslationService(translation_provider=fake_port)

    cues = [
        SubtitleCue(index=1, scene_index=0, start_time=0.0, end_time=2.0, text="Hello"),
        SubtitleCue(index=2, scene_index=0, start_time=2.0, end_time=4.0, text="World"),
    ]
    source = SubtitleTrack(id="sub-1", scene_plan_id="plan-1", cues=cues, total_duration_seconds=4.0)

    with pytest.raises(SubtitleTranslationError, match="mismatch"):
        await service.translate(source, "de")
