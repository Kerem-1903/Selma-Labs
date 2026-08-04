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

from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitleCue:
    index: int
    scene_index: int
    start_time: float
    end_time: float
    text: str
