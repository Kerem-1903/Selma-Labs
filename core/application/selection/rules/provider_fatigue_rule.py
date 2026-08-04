from core.application.selection.selection_rule import SelectionRule
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.selection_context import SelectionContext
import math

class ProviderFatigueRule(SelectionRule):
    def __init__(self, penalty_per_occurrence: float):
        if not math.isfinite(penalty_per_occurrence) or not 0.0 <= penalty_per_occurrence <= 1.0:
            raise ValueError("Penalty must be finite and between 0.0 and 1.0")
        self.penalty_per_occurrence = penalty_per_occurrence

    def calculate_penalty(self, candidate: ScoredAsset, context: SelectionContext) -> float:
        if not candidate.asset.provider or not context.recent_providers:
            return 0.0

        count = context.recent_providers.count(candidate.asset.provider.lower())
        return min(1.0, count * self.penalty_per_occurrence)
