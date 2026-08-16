from core.application.services.visual_intent_localization_service import (
    VisualIntentLocalizationService,
)
from core.domain.value_objects.visual_intent import VisualIntent


class FakeTranslationProvider:
    provider_identity = "fake:translation"

    async def translate_texts(self, texts, target_language):
        assert target_language == "English"
        mapping = {
            "ahtapotlar": "octopuses",
            "dolaşım": "circulation",
            "kalpleri": "hearts",
            "Ahtapotların neden üç kalbi var?": "Why do octopuses have three hearts?",
        }
        return [mapping[text] for text in texts]


async def test_localizes_unique_visual_terms_and_preserves_editorial_timing():
    service = VisualIntentLocalizationService(FakeTranslationProvider())
    intents = [
        VisualIntent(
            primary_keyword="ahtapotlar",
            secondary_keywords=("dolaşım", "kalpleri"),
            mood="reflective",
            motion_type="steady",
            start_ms=100,
            end_ms=2000,
            narrative_role="hook",
            shot_type="macro-close-up",
            narration_text="Ahtapotların üç kalbi vardır.",
            visual_job="locate_part",
            required_subjects=("ahtapotlar",),
            required_actions=("dolaşım",),
            required_relations=("kalpleri",),
            explanation_mode="hybrid",
            overlay_labels=("3 KALP",),
            explanatory_required=True,
        )
    ]

    localized = await service.localize(
        intents, source_anchor="Ahtapotların neden üç kalbi var?"
    )

    assert localized[0].search_query == (
        "octopuses hearts circulation macro close up"
    )
    assert localized[0].start_ms == 100
    assert localized[0].end_ms == 2000
    assert localized[0].narrative_role == "hook"
    assert localized[0].required_subjects == ("octopuses",)
    assert localized[0].required_actions == ("circulation",)
    assert localized[0].required_relations == ("hearts",)
    assert localized[0].overlay_labels == ("3 KALP",)


async def test_required_subject_outranks_question_adjectives_as_anchor():
    class VenusTranslationProvider:
        provider_identity = "fake:translation"

        async def translate_texts(self, texts, target_language):
            mapping = {
                "venüs'te": "on Venus",
                "uzun": "longer",
                "Venüs'te bir gün neden bir yıldan uzun?": (
                    "Why is a day on Venus longer than a year?"
                ),
            }
            return [mapping[text] for text in texts]

    intent = VisualIntent(
        primary_keyword="uzun",
        required_subjects=("venüs'te",),
        mood="reflective",
        motion_type="steady",
    )

    localized = await VisualIntentLocalizationService(
        VenusTranslationProvider()
    ).localize(
        [intent],
        source_anchor="Venüs'te bir gün neden bir yıldan uzun?",
    )

    assert localized[0].primary_keyword == "venus"
    assert localized[0].secondary_keywords[0] == "longer"
