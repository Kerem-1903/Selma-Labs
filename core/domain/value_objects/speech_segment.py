"""
SpeechSegment — one timed chunk of narration.

Optional metadata: a provider that can report word/sentence-level timing
(most can, to varying granularity) populates a list of these; a provider
that cannot leaves the list empty. Nothing downstream is required to use
this today — it exists so Sprint 3+ (scene planning, subtitle timing) can
consume it without a breaking change to VoiceTrack/GeneratedAudio when a
timing-capable provider is wired in.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeechSegment:
    text: str
    start: float
    end: float
