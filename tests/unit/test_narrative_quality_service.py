from __future__ import annotations

import pytest

from core.application.services.narrative_quality_service import NarrativeQualityService
from core.domain.entities.script import Script
from core.domain.exceptions import NarrativeQualityError
from core.domain.value_objects.narrative_quality_report import NarrativeQualityReport


def make_script(text: str, *, topic: str, duration: int = 24) -> Script:
    return Script.create(
        topic=topic,
        full_text=text,
        target_duration_seconds=duration,
        provider_used="fake:script",
    )


def test_turkish_why_script_builds_contract_beats_and_answer_evidence():
    script = make_script(
        (
            "Ahtapotun üç kalbi olması tesadüf değil. "
            "Çünkü iki kalp kanı solungaçlara gönderirken üçüncü kalp vücudu besliyor. "
            "Bu düzen, oksijenin bütün vücuda taşınmasını sürdürüyor."
        ),
        topic="Ahtapotların neden üç kalbi var?",
    )

    enriched, report = NarrativeQualityService().validate(script, language="tr")

    assert report.passed is True
    assert report.score == 15
    assert report.answer_evidence is not None
    assert report.answer_evidence.startswith("Çünkü")
    assert enriched.narrative_contract == report.contract
    assert [beat.role for beat in enriched.narrative_beats] == [
        "hook",
        "evidence",
        "payoff",
    ]
    assert enriched.narrative_beats[1].contains_answer is True


def test_octopus_baseline_is_blocked_for_weak_hook_unanswered_title_and_filler():
    script = make_script(
        (
            "Ahtapotlar kapalı dolaşım sistemine sahiptirler. "
            "Üç kalpleri vardır: bir sistemik kalp ve iki solungaç kalbi. "
            "Bu sistem kan dolaşımını sağlar. "
            "Bu özel sistem merak uyandırabilir. "
            "Şimdi bu ilginç yaratıkların dünyasına biraz daha yakından bakalım "
            "ve nasıl yaşadıklarını keşfetmeye çalışalım."
        ),
        topic="Ahtapotların neden üç kalbi var?",
    )

    _, report = NarrativeQualityService().evaluate(script, language="tr")

    codes = {issue.code for issue in report.issues}
    assert report.passed is False
    assert report.score < 8
    assert "weak_hook" in codes
    assert "unanswered_title_question" in codes
    assert "filler_sentence" in codes
    assert "weak_payoff" in codes


def test_validate_fails_closed_before_voice_generation():
    script = make_script(
        "Ahtapotlar denizde yaşar. Bu konu oldukça ilginçtir. Keşfedelim.",
        topic="Ahtapotlar neden renk değiştirir?",
    )

    with pytest.raises(NarrativeQualityError, match="Narrative contract failed"):
        NarrativeQualityService().validate(script, language="tr")


def test_explicit_longer_duration_is_recorded_but_does_not_block_strong_script():
    script = make_script(
        (
            "Why does an octopus need three hearts? "
            "Because two hearts move blood through the gills while the third supplies the body. "
            "That division keeps oxygen moving through its organs."
        ),
        topic="Why do octopuses have three hearts?",
        duration=30,
    )

    enriched, report = NarrativeQualityService().validate(script, language="en")

    assert report.passed is True
    assert report.score == 14
    assert enriched.narrative_contract is not None
    assert enriched.narrative_contract.duration_override_reason is not None
    assert {issue.code for issue in report.issues} == {"duration_override"}


def test_narrative_metadata_survives_script_creation_without_changing_identity():
    script = make_script(
        (
            "Why can this tiny animal survive the cold? "
            "Because antifreeze proteins stop damaging ice crystals from growing. "
            "That molecular shield keeps its cells intact."
        ),
        topic="Why can this animal survive freezing water?",
    )
    enriched, report = NarrativeQualityService().validate(script, language="en")

    assert enriched.id == script.id
    assert enriched.full_text == script.full_text
    assert enriched.narrative_contract == report.contract
    assert tuple(beat.text for beat in enriched.narrative_beats)
    assert NarrativeQualityReport.from_dict(report.to_dict()) == report
