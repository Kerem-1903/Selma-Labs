from dataclasses import dataclass

@dataclass(frozen=True)
class AssetScore:
    final_score: float
