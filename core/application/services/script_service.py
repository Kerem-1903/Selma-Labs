"""
ScriptService — application-layer orchestration for script generation.

This is where business rules live, deliberately separate from the provider
adapter. The adapter's job is "talk to Claude and translate the response
into a Script." This service's job is "decide whether that Script is
actually usable" — input validation and output validation that must apply
regardless of which provider generated the text. If the rules lived inside
the adapter, switching providers would mean re-implementing them (and
risking them drifting apart between providers).
"""
from __future__ import annotations

import logging

from core.domain.entities.script import Script
from core.domain.exceptions import ScriptGenerationError
from core.domain.ports.script_generator_port import ScriptGeneratorPort

logger = logging.getLogger("selma.script_service")

# Average spoken narration pace. Used only as a sanity bound to catch a
# provider ignoring the duration constraint (e.g. writing a 20-word script
# for a 60-second target) — not treated as ground truth. Voice generation
# in a later sprint measures actual audio duration, which is authoritative.
AVERAGE_WORDS_PER_MINUTE = 150
MIN_WORD_COUNT_RATIO = 0.5
MAX_WORD_COUNT_RATIO = 1.6

MIN_DURATION_SECONDS = 15
MAX_DURATION_SECONDS = 90


class ScriptService:
    """Generates and validates narration scripts via an injected provider."""

    def __init__(self, provider: ScriptGeneratorPort) -> None:
        self._provider = provider

    async def generate(self, topic: str, target_duration_seconds: int = 45) -> Script:
        """Generate a validated Script for ``topic``.

        Raises:
            ScriptGenerationError: Input was invalid, or the provider's
                output failed validation (empty, or a word count wildly
                inconsistent with the requested duration).
            ProviderError: Propagated unchanged from the adapter for
                transient/auth/quota failures — callers (e.g. a future
                Celery task) need the typed subclass to decide whether to
                retry.
        """
        topic = (topic or "").strip()
        if not topic:
            raise ScriptGenerationError("Topic must not be empty.")

        if not (MIN_DURATION_SECONDS <= target_duration_seconds <= MAX_DURATION_SECONDS):
            raise ScriptGenerationError(
                f"target_duration_seconds must be between {MIN_DURATION_SECONDS} and "
                f"{MAX_DURATION_SECONDS} for a Shorts-format video, got {target_duration_seconds}."
            )

        logger.info(
            "script_generation_started",
            extra={"topic": topic, "target_duration_seconds": target_duration_seconds},
        )

        script = await self._provider.generate_script(
            topic=topic, target_duration_seconds=target_duration_seconds
        )

        self._validate_output(script, target_duration_seconds)

        logger.info(
            "script_generation_completed",
            extra={"topic": topic, "word_count": script.estimated_word_count},
        )
        return script

    @staticmethod
    def _validate_output(script: Script, target_duration_seconds: int) -> None:
        if not script.full_text:
            raise ScriptGenerationError("Provider returned an empty script.")

        expected_words = (target_duration_seconds / 60) * AVERAGE_WORDS_PER_MINUTE
        min_words = expected_words * MIN_WORD_COUNT_RATIO
        max_words = expected_words * MAX_WORD_COUNT_RATIO

        if not (min_words <= script.estimated_word_count <= max_words):
            raise ScriptGenerationError(
                f"Generated script has {script.estimated_word_count} words, outside the "
                f"expected range ({min_words:.0f}-{max_words:.0f} words) for a "
                f"{target_duration_seconds}s narration. This usually means the provider "
                "ignored the duration constraint — reject and retry rather than using it."
            )
