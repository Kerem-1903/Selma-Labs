"""
ScenePlanningPort — the contract every scene-planning provider must
satisfy.

Same role as ScriptGeneratorPort/VoiceGeneratorPort/VideoSourcePort:
ScenePlanningService depends only on this interface, never on a concrete
provider like Claude. Swapping providers means writing one new adapter
class and a branch in config/provider_registry.py — no other file changes.

Deliberately provider-independent about WHAT it asks for: this Port takes
plain narration text, not a Script entity — consistent with every other
Port in this codebase (ScriptGeneratorPort takes a topic string,
VoiceGeneratorPort takes text), so an adapter never depends on an unrelated
entity's shape.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.scene import Scene


class ScenePlanningPort(ABC):
    """Breaks narration text into a sequence of semantic visual scenes."""

    @property
    @abstractmethod
    def provider_identity(self) -> str:
        """A short string identifying which provider/model produced a
        scene plan, e.g. "anthropic:claude-sonnet-4-5". Carried through
        onto ScenePlan.provider_used by ScenePlanningService — same
        purpose as Script.provider_used and VoiceTrack.provider."""
        raise NotImplementedError

    @abstractmethod
    async def plan_scenes(self, narration_text: str) -> list[Scene]:
        """Break ``narration_text`` into logical visual scenes.

        Implementations decide how to segment the narration — grouping
        related sentences into one scene rather than splitting mechanically
        on every sentence — and populate each Scene's narration,
        search_keywords, detected_objects, location, mood, and
        visual_priority fields.

        Deliberately does NOT estimate timing: an LLM has no reliable sense
        of elapsed seconds. Every returned Scene's start_time/end_time are
        left at their defaults (0.0) — ScenePlanningService computes real
        timing afterwards from VoiceTrack.duration_seconds, a genuinely
        measured value this Port has no access to.

        Args:
            narration_text: The full narration script text to segment.

        Returns:
            An ordered list of Scene objects. List position is the
            intended scene order — ScenePlanningService re-derives each
            Scene's final ``index`` from this order rather than trusting
            any index a provider may echo back.

        Raises:
            ProviderAuthError: Credentials invalid/missing.
            ProviderTimeoutError: Provider did not respond in time.
            ProviderConnectionError: Could not reach the provider at all.
            ProviderQuotaExceededError: Rate limit or quota exceeded.
            ScenePlanningError: The provider's raw response could not be
                parsed into scenes at all (e.g. invalid JSON, or not a
                list) — distinct from ProviderError, since the request
                itself succeeded; this is a content problem, not a
                connectivity one.
            ProviderError: Any other provider-side failure.
        """
        raise NotImplementedError
