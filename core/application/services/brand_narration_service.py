"""Apply a short, repeatable channel signature without weakening the hook."""
from __future__ import annotations

import re
from dataclasses import replace

from core.domain.entities.script import Script
from core.domain.value_objects.narrative_contract import NarrativeBeat


class BrandNarrationService:
    """Insert a compact spoken identity immediately after the opening hook.

    The factual script is verified before this service runs.  The signature is
    deliberately inserted after the first sentence so the first spoken words
    still deliver the video's promise instead of spending the hook on branding.
    """

    _SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?…])\s+")

    def __init__(self, signature: str = "Welcome to Strange Things.") -> None:
        cleaned = " ".join(signature.split()).strip()
        if not cleaned:
            raise ValueError("Brand signature must not be empty.")
        if len(cleaned.split()) > 6:
            raise ValueError("Brand signature must be six words or fewer.")
        self._signature = cleaned

    @property
    def signature(self) -> str:
        return self._signature

    def apply(self, script: Script) -> Script:
        """Return ``script`` with one idempotent post-hook signature."""
        text = " ".join(script.full_text.split()).strip()
        if not text:
            return script
        if self._normalize(self._signature) in self._normalize(text):
            return script

        sentences = self._SENTENCE_BOUNDARY.split(text, maxsplit=1)
        branded_text = (
            f"{sentences[0]} {self._signature} {sentences[1]}"
            if len(sentences) == 2
            else f"{text} {self._signature}"
        )
        beats = self._insert_brand_beat(script.narrative_beats)
        return replace(
            script,
            full_text=branded_text,
            estimated_word_count=len(branded_text.split()),
            narrative_beats=beats,
        )

    def _insert_brand_beat(
        self,
        beats: tuple[NarrativeBeat, ...],
    ) -> tuple[NarrativeBeat, ...]:
        if not beats:
            return ()
        hook_position = next(
            (index for index, beat in enumerate(beats) if beat.role == "hook"),
            0,
        )
        ordered = list(beats)
        ordered.insert(
            hook_position + 1,
            NarrativeBeat(
                index=hook_position + 1,
                role="brand_signature",
                text=self._signature,
                information_contribution="Recurring spoken channel identity.",
                contains_answer=False,
            ),
        )
        return tuple(replace(beat, index=index) for index, beat in enumerate(ordered))

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^\w]+", " ", text.casefold(), flags=re.UNICODE).strip()
