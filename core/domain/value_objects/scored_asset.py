from dataclasses import dataclass
from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.asset_score import AssetScore

@dataclass(frozen=True)
class ScoredAsset:
    asset: MediaAsset
    score: AssetScore
