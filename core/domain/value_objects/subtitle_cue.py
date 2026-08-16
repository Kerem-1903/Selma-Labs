"""
SubtitleCue — one on-screen caption block within a SubtitleTrack.

Value object, not entity — no identity of its own beyond its position in
the parent's list, same relationship Scene has to ScenePlan and
TimelineClip has to Timeline.

``scene_index`` (an ``int``), not the full ``Scene`` object, is
deliberately what this carries for traceability back to its source --
a real deviation from the TimelineClip/SceneAssetMatch precedent of
embedding the whole Scene, and it deserves the same scrutiny given to any
deviation from an established pattern in this codebase:

TimelineClip/SceneAssetMatch have a strict 1:1 cardinality with their
Scene -- one clip, one match, per scene -- so embedding the full object
costs nothing and saves a lookup. SubtitleCue does not have that
cardinality: a single Scene's narration is frequently split into several
cues (see SubtitleService.generate()), so embedding the full Scene on
every resulting cue would duplicate that Scene's narration/
search_keywords/mood/etc. across N cues for one scene -- data nothing
downstream of a SubtitleCue actually reads. ``scene_index`` is enough for
traceability, consistent with Scene.index itself being "positional
bookkeeping, not a generated identity," not domain content.

Cues never cross a Scene boundary (see SubtitleService.generate()'s own
docstring for why) -- every cue's ``start_time``/``end_time`` falls
entirely within the ``start_time``/``end_time`` of the one Scene named by
``scene_index``.

``text`` is already fully formatted for on-screen display: split into
readable lines (at most SubtitleService's configured
``max_lines_per_cue``), each within ``max_chars_per_line``, joined with
``"\\n"``. Nothing downstream re-wraps it -- the same "compute it once,
carry the finished value" principle Scene.finalize() already applies to
timing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.value_objects.word_timing import WordTiming


@dataclass(frozen=True)
class SubtitleCue:
    """One on-screen subtitle block.

    ``words`` is the authoritative source for premium karaoke cues. Legacy
    narration cues may omit it while the existing SRT/VTT pipeline migrates;
    in that mode their second-based fields remain backward-compatible.
    """

    index: int = 0
    scene_index: int = -1
    start_time: float = 0.0
    end_time: float = 0.0
    text: str = ""
    words: list[WordTiming] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.words:
            return
        if any(
            later.start_ms < earlier.start_ms
            for earlier, later in zip(self.words, self.words[1:])
        ):
            raise ValueError("SubtitleCue words must be ordered by start_ms.")
        object.__setattr__(self, "start_time", self.words[0].start_ms / 1_000)
        object.__setattr__(self, "end_time", self.words[-1].end_ms / 1_000)
        object.__setattr__(self, "text", " ".join(word.text for word in self.words))

    @classmethod
    def from_words(
        cls,
        words: list[WordTiming],
        *,
        index: int = 0,
        scene_index: int = -1,
    ) -> "SubtitleCue":
        """Create one word-timed cue with derived display text and timing."""
        if not words:
            raise ValueError("SubtitleCue requires at least one WordTiming.")
        return cls(index=index, scene_index=scene_index, words=list(words))

    @property
    def start_ms(self) -> int:
        """Cue start derived from its first word when word timing is present."""
        return self.words[0].start_ms if self.words else round(self.start_time * 1_000)

    @property
    def end_ms(self) -> int:
        """Cue end derived from its final word when word timing is present."""
        return self.words[-1].end_ms if self.words else round(self.end_time * 1_000)

    @property
    def duration_ms(self) -> int:
        """Return the on-screen duration in milliseconds."""
        return self.end_ms - self.start_ms

    @property
    def word_count(self) -> int:
        """Return the number of timed words, or legacy display words as fallback."""
        return len(self.words) if self.words else len(self.text.replace("\n", " ").split())
