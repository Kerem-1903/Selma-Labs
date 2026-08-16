from __future__ import annotations

import pytest

from core.domain.exceptions import InvalidVoiceConfigurationError
from core.domain.value_objects.voice_direction import VoiceDirection
from infrastructure.providers.voice.elevenlabs_provider import ElevenLabsVoiceProvider


def test_strange_things_voice_profile_includes_controlled_short_form_speed():
    provider = ElevenLabsVoiceProvider(
        api_key="test-key",
        stability=0.35,
        similarity_boost=0.8,
        style=0.45,
        speed=1.05,
    )

    assert provider._voice_settings == {
        "stability": 0.35,
        "similarity_boost": 0.8,
        "style": 0.45,
        "speed": 1.05,
        "use_speaker_boost": True,
    }


@pytest.mark.parametrize("speed", [0.69, 1.21])
def test_voice_profile_rejects_unsupported_speed(speed):
    with pytest.raises(InvalidVoiceConfigurationError, match="speed"):
        ElevenLabsVoiceProvider(api_key="test-key", speed=speed)


def test_timestamp_alignment_is_grouped_into_exact_word_segments():
    segments = ElevenLabsVoiceProvider._word_segments(
        {
            "characters": list("Hello world!"),
            "character_start_times_seconds": [index / 10 for index in range(12)],
            "character_end_times_seconds": [(index + 1) / 10 for index in range(12)],
        }
    )

    assert [(segment.text, segment.start, segment.end) for segment in segments] == [
        ("Hello", 0.0, 0.5),
        ("world!", 0.6, 1.2),
    ]


def test_provider_translates_direction_into_native_voice_settings():
    provider = ElevenLabsVoiceProvider(api_key="test-key")
    direction = VoiceDirection(
        profile="mystery",
        speed=1.02,
        stability=0.42,
        style=0.48,
        maximum_pause_ms=450,
        hook_delivery="quiet_precise_tension",
        explanation_delivery="clear_with_controlled_suspense",
        payoff_delivery="slow_down_on_the_reveal",
    )

    settings = provider._settings_for_direction(direction)

    assert settings["speed"] == 1.02
    assert settings["stability"] == 0.42
    assert settings["style"] == 0.48
    assert settings["similarity_boost"] == 0.8
