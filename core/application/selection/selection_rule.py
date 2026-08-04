from abc import ABC, abstractmethod
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.selection_context import SelectionContext

class SelectionRule(ABC):
    @abstractmethod
    def calculate_penalty(self, candidate: ScoredAsset, context: SelectionContext) -> float:
        pass
