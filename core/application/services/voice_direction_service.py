"""Select a repeatable narration profile from verified editorial evidence."""
from __future__ import annotations

from core.domain.entities.script import Script
from core.domain.value_objects.voice_direction import VoiceDirection


_ENERGY_MARKERS = {
    "speed", "power", "technology", "experiment", "electric", "explosion",
    "hız", "güç", "teknoloji", "deney", "elektrik", "patlama",
}
_MYSTERY_MARKERS = {
    "unknown", "secret", "mystery", "dark", "ancient", "space", "ocean",
    "bilinmeyen", "sır", "gizem", "karanlık", "antik", "uzay", "okyanus",
}
_DOCUMENTARY_MARKERS = {
    "history", "war", "empire", "archive", "research", "study",
    "tarih", "savaş", "imparatorluk", "arşiv", "araştırma", "çalışma",
}


class VoiceDirectionService:
    """Derive tone and tempo without embedding provider-specific settings."""

    def plan(self, script: Script) -> VoiceDirection:
        corpus = f"{script.topic} {script.full_text}".casefold()
        if any(marker in corpus for marker in _ENERGY_MARKERS):
            profile = "energy"
            speed, stability, style = 1.07, 0.32, 0.55
            hook = "urgent_but_controlled"
            explanation = "fast_clear_and_precise"
            payoff = "confident_short_landing"
        elif any(marker in corpus for marker in _DOCUMENTARY_MARKERS):
            profile = "documentary"
            speed, stability, style = 1.00, 0.48, 0.32
            hook = "measured_consequence"
            explanation = "authoritative_and_unhurried"
            payoff = "firm_reflective_landing"
        elif any(marker in corpus for marker in _MYSTERY_MARKERS):
            profile = "mystery"
            speed, stability, style = 1.02, 0.42, 0.48
            hook = "quiet_precise_tension"
            explanation = "clear_with_controlled_suspense"
            payoff = "slow_down_on_the_reveal"
        else:
            profile = "wonder"
            speed, stability, style = 1.04, 0.38, 0.42
            hook = "bright_curiosity"
            explanation = "warm_clear_explanation"
            payoff = "satisfying_smile_in_the_voice"

        if script.target_duration_seconds > 60:
            speed = max(0.98, speed - 0.03)
        return VoiceDirection(
            profile=profile,
            speed=round(speed, 2),
            stability=stability,
            style=style,
            maximum_pause_ms=550 if script.target_duration_seconds > 60 else 450,
            hook_delivery=hook,
            explanation_delivery=explanation,
            payoff_delivery=payoff,
        )
