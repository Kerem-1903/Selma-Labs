import logging
import math
from typing import Sequence
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.adjusted_asset_score import AdjustedAssetScore
from core.domain.value_objects.selection_context import SelectionContext
from core.application.selection.selection_rule import SelectionRule

logger = logging.getLogger(__name__)

class AssetSelectionService:
    def __init__(self, rules: Sequence[SelectionRule], provider_window: int = 3, keyword_window: int = 15, top_k: int = 5):
        if any(not isinstance(r, SelectionRule) for r in rules):
            raise TypeError("All rules must be instances of SelectionRule")
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")

        self._rules = tuple(rules)
        self._provider_window = provider_window
        self._keyword_window = keyword_window
        self._top_k = top_k

    def select_for_timeline(self, timeline_candidates: Sequence[tuple[Scene, list[ScoredAsset]]]) -> list[tuple[Scene, list[AdjustedAssetScore]]]:
        context = SelectionContext()
        result = []

        for scene, candidates in timeline_candidates:
            if not candidates:
                result.append((scene, []))
                continue

            adjusted_candidates = []
            for candidate in candidates:
                total_penalty = 0.0
                penalties: dict[str, float] | None = None  # LAZY ALLOCATION & STRICT TYPE SAFETY

                for rule in self._rules:
                    try:
                        p = rule.calculate_penalty(candidate, context)
                    except Exception:
                        logger.exception("Error applying selection rule '%s'", rule.__class__.__name__)
                        p = 0.0

                    p = max(0.0, min(1.0, p if math.isfinite(p) else 0.0))
                    if p > 0.0:
                        if penalties is None:
                            penalties = {}
                        penalties[rule.__class__.__name__] = p
                        total_penalty += p

                adj_score = max(0.0, min(1.0, candidate.score.final_score - total_penalty))
                adjusted_candidates.append((adj_score, candidate, penalties))

            # Attribute overhead'inden kaçınmak için primitive tuple sıralaması kullanıyoruz
            adjusted_candidates.sort(key=lambda x: (-x[0], -x[1].score.final_score, x[1].asset.id))

            # Sadece en iyi K aday için obje instance'ı yaratılıyor (GC Memory Churn Optimizasyonu)
            top_candidates = adjusted_candidates[:self._top_k]

            final_scene_candidates = [
                # Servis optimizasyon detayını (singleton proxy) bilmez, sadece veriyi atar.
                AdjustedAssetScore(original=cand, penalties=pens, adjusted_score=adj)
                for adj, cand, pens in top_candidates
            ]

            context = context.with_asset(final_scene_candidates[0].original.asset, self._provider_window, self._keyword_window)
            result.append((scene, final_scene_candidates))

        return result
