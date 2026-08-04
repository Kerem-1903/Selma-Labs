"""
SceneAssetMatch — one Scene paired with its ranked candidate MediaAssets.

Value object, not entity — same relationship to AssetMatchPlan that Scene
has to ScenePlan and SpeechSegment has to VoiceTrack: no identity of its
own, just an ordered element of its parent's list.

``scene`` is carried through in full (not just its index) so a consumer of
one SceneAssetMatch never needs to reach back into a separate ScenePlan to
know what it was matched against — the same reasoning GeneratedAudio uses
for embedding full SpeechSegment objects rather than just offsets.

``assets`` is ranked best-first by SceneAssetMatchingService's deterministic
heuristic scoring (keyword overlap, orientation, duration fit — see that
service's docstring) and MAY BE EMPTY. An empty list is a valid, expected
outcome — "no candidates found for this scene's keywords" — not an error.
Every asset in this list has ``local_path is None``: Sprint 5 matches and
ranks candidates, it does not download them. Downloading only the
eventually-selected asset per scene is later-sprint (Video Assembly) work.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.scene import Scene


@dataclass(frozen=True)
class SceneAssetMatch:
    scene: Scene
    assets: list[MediaAsset]

    @property
    def has_matches(self) -> bool:
        """True if at least one candidate asset was found for this scene.

        A small convenience for consumers (CLI output, a future selection
        step) that need to distinguish "matched" from "unmatched" scenes
        without repeating ``len(assets) > 0`` at every call site — not a
        stored field, since it is always cheaply derivable from ``assets``.
        """
        return len(self.assets) > 0
