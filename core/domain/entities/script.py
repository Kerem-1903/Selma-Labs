"""
Script entity.

A Script is the narration text for one SELMA Shorts video, before it has been
split into timed scenes (scene-splitting is a later sprint). It is intentionally
a plain, framework-free dataclass — no ORM, no Pydantic — because the domain
layer must not know that a database or an API will ever exist.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from core.domain.value_objects.narrative_contract import NarrativeBeat, NarrativeContract


@dataclass(frozen=True)
class Script:
    """Immutable representation of a generated narration script."""

    id: str
    topic: str
    full_text: str
    target_duration_seconds: int
    estimated_word_count: int
    provider_used: str
    created_at: datetime
    narrative_contract: NarrativeContract | None = None
    narrative_beats: tuple[NarrativeBeat, ...] = ()

    @staticmethod
    def create(
        *,
        topic: str,
        full_text: str,
        target_duration_seconds: int,
        provider_used: str,
        narrative_contract: NarrativeContract | None = None,
        narrative_beats: tuple[NarrativeBeat, ...] = (),
    ) -> "Script":
        """Factory that derives word count and stamps identity/creation time.

        Kept as a factory (rather than a plain constructor call) so that
        every code path that creates a Script computes word_count the same
        way — duplicating that calculation at each call site is exactly the
        kind of logic drift the founder prompt asked us to avoid.
        """
        cleaned_text = full_text.strip()
        return Script(
            id=str(uuid.uuid4()),
            topic=topic,
            full_text=cleaned_text,
            target_duration_seconds=target_duration_seconds,
            estimated_word_count=len(cleaned_text.split()),
            provider_used=provider_used,
            created_at=datetime.now(timezone.utc),
            narrative_contract=narrative_contract,
            narrative_beats=tuple(narrative_beats),
        )

    def with_narrative(
        self,
        contract: NarrativeContract,
        beats: tuple[NarrativeBeat, ...],
    ) -> "Script":
        """Attach validated creative metadata without changing script identity."""
        return replace(
            self,
            narrative_contract=contract,
            narrative_beats=tuple(beats),
        )
