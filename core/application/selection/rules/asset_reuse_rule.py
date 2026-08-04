from core.application.selection.selection_rule import SelectionRule
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.selection_context import SelectionContext
import math

class AssetReuseRule(SelectionRule):
    def __init__(self, penalty: float):
        if not math.isfinite(penalty) or not 0.0 <= penalty <= 1.0:
            raise ValueError("Penalty must be finite and between 0.0 and 1.0")
        self.penalty = penalty

    def calculate_penalty(self, candidate: ScoredAsset, context: SelectionContext) -> float:
        if candidate.asset.id in context.used_asset_ids:
            return self.penalty
        return 0.0
