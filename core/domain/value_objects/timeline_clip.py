"""
TimelineClip — one Scene paired with its final, downloaded MediaAsset,
ready to be handed to a future rendering step.

Value object, not entity — same relationship to Timeline that Scene has to
ScenePlan and SceneAssetMatch has to AssetMatchPlan: no identity of its
own, just an ordered element of its parent's list.

``scene`` is carried through in full (not just its index), same reasoning
SceneAssetMatch already documents for doing the same thing — a consumer of
one TimelineClip never needs to reach back into a separate ScenePlan to
know what it covers. Timing (``start_time``/``end_time``) is deliberately
NOT duplicated onto TimelineClip itself — ``scene.start_time``/
``scene.end_time`` are already the authoritative, finalized values
(ScenePlanningService.finalize() computed them from real VoiceTrack
duration); storing a second copy here would create two sources of truth
for the same number. A consumer reads ``clip.scene.start_time`` the same
way it already reads ``clip.scene.narration``.

``asset`` is the single MediaAsset TimelineService selected from that
scene's ranked SceneAssetMatch.assets (best-ranked, i.e. assets[0]) and
downloaded via VideoSearchService — unlike the candidates inside
SceneAssetMatch, this asset's ``local_path`` is always set.

``metadata`` (Sprint 6): an open, unvalidated extension point for
per-clip rendering attributes a future sprint may need — e.g. transition
type, playback speed, zoom/pan, crop mode, effects, subtitle placement.
None of that exists yet, and none of it is guessed at here: the concrete
shape of "camera motion" or "transition" is likely to end up as a small
typed value object of its own once a real rendering sprint defines it, not
a loose float/string field guessed at today. Deliberately untyped
(``dict[str, Any]``) and empty by default — same reasoning MediaAsset.metadata
(Sprint 3.1) already established in this codebase for exactly this
situation: future schema, not yet known, so don't commit to one.

No service reads, writes, or validates this field in this sprint. It
exists purely so a future rendering sprint can evolve the data model
without forcing a breaking change to Timeline/TimelineClip's shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.scene import Scene


@dataclass(frozen=True)
class TimelineClip:
    scene: Scene
    asset: MediaAsset
    # Extension point only — see module docstring. Not read, written, or
    # validated by any service in this sprint.
    metadata: dict[str, Any] = field(default_factory=dict)
