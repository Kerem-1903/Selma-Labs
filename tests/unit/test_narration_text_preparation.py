from core.application.services.narration_text_preparation_service import NarrationTextPreparationService
from core.domain.entities.script import Script


def test_prepares_turkish_symbols_and_channel_pronunciations(tmp_path):
    lexicon = tmp_path / "lexicon.json"
    lexicon.write_text('{"tr":{"Mars":"Mers"}}', encoding="utf-8")
    script = Script.create(
        topic="Mars ve DNA",
        full_text="Mars’ta DNA oranı %20 mi??",
        target_duration_seconds=20,
        provider_used="test",
    )

    result = NarrationTextPreparationService(lexicon).prepare(script)

    assert result.language == "tr"
    assert result.spoken_text == "Mers’ta de ne a oranı yüzde 20 mi?"
    assert ("DNA", "de ne a") in result.replacements
