from core.application.services.voice_direction_service import VoiceDirectionService
from core.domain.entities.script import Script
from core.domain.value_objects.voice_direction import VoiceDirection


def _script(topic: str, text: str, *, duration: int = 24) -> Script:
    return Script.create(
        topic=topic,
        full_text=text,
        target_duration_seconds=duration,
        provider_used="test",
    )


def test_energy_topic_receives_faster_more_expressive_direction():
    direction = VoiceDirectionService().plan(
        _script(
            "Yeni elektrik deneyi",
            "Bu teknoloji enerjiyi çok daha hızlı aktarıyor.",
        )
    )

    assert direction.profile == "energy"
    assert direction.speed == 1.07
    assert direction.maximum_pause_ms == 450
    assert VoiceDirection.from_dict(direction.to_dict()) == direction


def test_long_documentary_slows_down_and_expands_pause_budget():
    direction = VoiceDirectionService().plan(
        _script(
            "Roma İmparatorluğu tarihi",
            "Arşiv kayıtları bu savaşın sonuçlarını gösteriyor.",
            duration=180,
        )
    )

    assert direction.profile == "documentary"
    assert direction.speed == 0.98
    assert direction.maximum_pause_ms == 550


def test_mystery_profile_uses_controlled_reveal_delivery():
    direction = VoiceDirectionService().plan(
        _script("Okyanusun karanlık sırrı", "Derinde bilinmeyen bir düzen var.")
    )

    assert direction.profile == "mystery"
    assert direction.payoff_delivery == "slow_down_on_the_reveal"
