"""
ScriptGeneratorPort — the contract every script-writing provider must satisfy.

This is the abstraction referenced throughout the architecture doc: the
application layer (ScriptService) and everything above it depends only on
this interface, never on a concrete provider like Claude or OpenAI. Swapping
providers means writing a new adapter class that implements this Protocol —
no other file in the codebase changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.entities.script import Script


class ScriptGeneratorPort(ABC):
    """Produces a narration-ready script for a given topic and duration."""

    @abstractmethod
    async def generate_script(
        self,
        topic: str,
        target_duration_seconds: int,
        language: str | None = None,
    ) -> Script:
        """Generate a spoken-narration script about ``topic``.

        Implementations are responsible for researching the topic (facts,
        angle, hook) and producing plain narration text suitable for
        text-to-speech — no stage directions, no markdown, no preamble.

        Args:
            topic: The subject to write about, e.g. "Why did the Roman
                Empire collapse?"
            target_duration_seconds: Desired spoken length, used by the
                implementation to target an appropriate word count.
            language: Optional output language code or name.

        Returns:
            A populated Script entity.

        Raises:
            ProviderAuthError: Credentials invalid/missing.
            ProviderTimeoutError: Provider did not respond in time.
            ProviderQuotaExceededError: Rate limit or quota exceeded.
            ProviderError: Any other provider-side failure.
        """
        raise NotImplementedError
