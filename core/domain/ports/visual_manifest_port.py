"""Port for operator-reviewed local visual collections."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.asset_diversity import AssetUsage
from core.domain.value_objects.visual_intent import VisualIntent


class VisualManifestPort(ABC):
    """Supplies one licensed, local clip for every planned visual beat."""

    @abstractmethod
    def select(
        self,
        visual_intents: Sequence[VisualIntent],
    ) -> tuple[list[MediaAsset], list[AssetUsage]]:
        """Return ordered local assets and their editorial usage evidence."""
        raise NotImplementedError
