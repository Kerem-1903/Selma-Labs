from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
import re
from typing import Any


@dataclass(frozen=True)
class StoryboardFrame:
    """Metadata for one generated keyframe; binary content stays in storage."""

    id: str
    shot_contract_id: str
    sequence_index: int
    media_asset_id: str
    storage_key: str
    content_type: str
    provider: str
    provider_asset_id: str
    width: int
    height: int
    reference_asset_ids: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.sequence_index < 0:
            raise ValueError("sequence_index cannot be negative.")
        normalized_key = self.storage_key.replace("\\", "/")
        key_path = PurePosixPath(normalized_key)
        if (
            not normalized_key
            or key_path.is_absolute()
            or re.match(r"^[A-Za-z]:", normalized_key)
            or any(part in {"", ".", ".."} for part in key_path.parts)
        ):
            raise ValueError("storage_key must be a portable relative key.")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Storyboard frame dimensions must be greater than zero.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "shot_contract_id": self.shot_contract_id,
            "sequence_index": self.sequence_index,
            "media_asset_id": self.media_asset_id,
            "storage_key": self.storage_key,
            "content_type": self.content_type,
            "provider": self.provider,
            "provider_asset_id": self.provider_asset_id,
            "width": self.width,
            "height": self.height,
            "reference_asset_ids": list(self.reference_asset_ids),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoryboardFrame":
        return cls(
            id=str(data["id"]),
            shot_contract_id=str(data["shot_contract_id"]),
            sequence_index=int(data["sequence_index"]),
            media_asset_id=str(data["media_asset_id"]),
            storage_key=str(data["storage_key"]),
            content_type=str(data["content_type"]),
            provider=str(data["provider"]),
            provider_asset_id=str(data.get("provider_asset_id", "")),
            width=int(data["width"]),
            height=int(data["height"]),
            reference_asset_ids=tuple(
                str(item) for item in data.get("reference_asset_ids", [])
            ),
            created_at=datetime.fromisoformat(str(data["created_at"])),
        )
