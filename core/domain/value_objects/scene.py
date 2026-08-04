"""
Scene — one semantic visual beat within a ScenePlan.

Value object, not entity — same relationship to ScenePlan that
SpeechSegment has to VoiceTrack: no identity of its own, just an ordered
element of its parent's list. ``index`` is positional bookkeeping, not a
generated identity.

``start_time``/``end_time`` default to 0.0 and are NOT set by
ScenePlanningPort implementations — an LLM has no reliable sense of
elapsed seconds. ScenePlanningService computes real timing afterwards from
VoiceTrack.duration_seconds (a genuinely measured value) and calls
``finalize`` to produce the timed version. This mirrors MediaAsset's
``local_path``/``with_local_path`` split from Sprint 3.1: one class, not a
raw/final pair, because everything except timing is already final the
moment the provider returns it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True)
class Scene:
    index: int
    narration: str
    search_keywords: list[str]
    detected_objects: list[str]
    location: Optional[str]
    mood: Optional[str]
    # "high" | "medium" | "low" — free-form str rather than a Literal/enum
    # because a provider adapter is responsible for normalizing whatever a
    # model returns into one of these three; the domain layer just carries
    # the already-normalized value through.
    visual_priority: str
    start_time: float = 0.0
    end_time: float = 0.0

    def finalize(self, index: int, start_time: float, end_time: float) -> "Scene":
        """Return a copy with ``index`` and timing set.

        Scene is frozen like every other domain object in this codebase;
        ScenePlanningService calls this once it has computed each scene's
        share of the total narration duration, and re-derives ``index``
        from list order rather than trusting whatever a provider echoed
        back (defensive against a malformed or gapped provider response).
        """
        return replace(self, index=index, start_time=start_time, end_time=end_time)
