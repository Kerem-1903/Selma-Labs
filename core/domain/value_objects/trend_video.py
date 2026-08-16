from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TrendVideo:
    video_id: str
    title: str
    description: str
    url: str
    channel_title: str
    published_at: str
    duration_seconds: float
    view_count: int
    like_count: int
    category_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "channel_title": self.channel_title,
            "published_at": self.published_at,
            "duration_seconds": self.duration_seconds,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "category_id": self.category_id,
        }
