from dataclasses import dataclass, field
from core.domain.entities.media_asset import MediaAsset

@dataclass(frozen=True)
class SelectionContext:
    used_asset_ids: frozenset[str] = field(default_factory=frozenset)
    recent_providers: tuple[str, ...] = field(default_factory=tuple)
    recent_keywords: tuple[str, ...] = field(default_factory=tuple)

    def with_asset(self, asset: MediaAsset, provider_window: int = 3, keyword_window: int = 15) -> "SelectionContext":
        new_ids = self.used_asset_ids | frozenset([asset.id])

        new_providers = self.recent_providers
        if asset.provider:
            new_providers = (self.recent_providers + (asset.provider.lower(),))[-provider_window:] if provider_window > 0 else tuple()

        new_keywords = self.recent_keywords
        if asset.tags:
            tags = tuple(t.lower() for t in asset.tags)
            new_keywords = (self.recent_keywords + tags)[-keyword_window:] if keyword_window > 0 else tuple()

        return SelectionContext(
            used_asset_ids=new_ids,
            recent_providers=new_providers,
            recent_keywords=new_keywords
        )
