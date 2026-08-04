from dataclasses import dataclass
from typing import Mapping
from types import MappingProxyType
import math
from core.domain.value_objects.scored_asset import ScoredAsset

_EMPTY_PENALTIES: Mapping[str, float] = MappingProxyType({})

@dataclass(frozen=True)
class AdjustedAssetScore:
    original: ScoredAsset
    penalties: Mapping[str, float] | None
    adjusted_score: float

    def __post_init__(self):
        # Encapsulation: Servis None veya {} gönderse bile,
        # GC optimizasyonu Value Object'in kendi sorumluluğundadır.
        if not self.penalties:
            object.__setattr__(self, "penalties", _EMPTY_PENALTIES)
        else:
            object.__setattr__(self, "penalties", MappingProxyType(dict(self.penalties)))

        if not math.isfinite(self.adjusted_score):
            raise ValueError(f"adjusted_score must be finite, got {self.adjusted_score}")
        if not 0.0 <= self.adjusted_score <= 1.0:
            raise ValueError(f"adjusted_score must be between 0.0 and 1.0, got {self.adjusted_score}")
