from core.application.selection.selection_rule import SelectionRule
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.selection_context import SelectionContext
import math

class KeywordFatigueRule(SelectionRule):
    def __init__(self, penalty_per_match: float):
        if not math.isfinite(penalty_per_match) or not 0.0 <= penalty_per_match <= 1.0:
            raise ValueError("Penalty must be finite and between 0.0 and 1.0")
        self.penalty_per_match = penalty_per_match

    def calculate_penalty(self, candidate: ScoredAsset, context: SelectionContext) -> float:
        if not candidate.asset.tags or not context.recent_keywords:
            return 0.0

        asset_tags = {t.lower() for t in candidate.asset.tags}
        matches = sum(context.recent_keywords.count(tag) for tag in asset_tags)
        return min(1.0, matches * self.penalty_per_match)
