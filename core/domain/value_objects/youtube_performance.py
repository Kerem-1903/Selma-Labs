"""Post-publish Shorts metrics used by SELMA's channel-specific learning loop."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class YoutubePerformanceRecord:
    video_id: str
    published_at: datetime
    content_format: str
    hook_type: str
    duration_seconds: float
    viewed_percentage: float
    engaged_views: int
    average_view_duration_seconds: float
    average_percentage_viewed: float
    subscribers_gained: int = 0
    retention_drop_timestamps: tuple[float, ...] = ()
    experiment_id: str | None = None
    experiment_variant: str | None = None
    distribution_started_at: datetime | None = None
    first_3_second_retention_percentage: float | None = None
    first_30_second_retention_percentage: float | None = None
    impressions_click_through_rate: float | None = None
    comment_question: str | None = None
    comments_count: int = 0
    title_style: str | None = None
    thumbnail_style: str | None = None

    def __post_init__(self) -> None:
        if not self.video_id.strip():
            raise ValueError("YouTube video id must not be empty.")
        if self.published_at.tzinfo is None:
            raise ValueError("published_at must include timezone information.")
        if not self.content_format.strip() or not self.hook_type.strip():
            raise ValueError("Content format and hook type must not be empty.")
        if self.duration_seconds <= 0:
            raise ValueError("Video duration must be greater than zero.")
        if not 0 <= self.viewed_percentage <= 100:
            raise ValueError("Viewed percentage must be between 0 and 100.")
        if self.engaged_views < 0 or self.subscribers_gained < 0:
            raise ValueError("View and subscriber counts must not be negative.")
        if self.comments_count < 0:
            raise ValueError("Comment count must not be negative.")
        if self.average_view_duration_seconds < 0 or self.average_percentage_viewed < 0:
            raise ValueError("Average viewing metrics must not be negative.")
        if any(value < 0 or value > self.duration_seconds for value in self.retention_drop_timestamps):
            raise ValueError("Retention drops must fall inside the video duration.")
        for name, value in (
            ("first_3_second_retention_percentage", self.first_3_second_retention_percentage),
            ("first_30_second_retention_percentage", self.first_30_second_retention_percentage),
            ("impressions_click_through_rate", self.impressions_click_through_rate),
        ):
            if value is not None and not 0 <= value <= 100:
                raise ValueError(f"{name} must be between 0 and 100.")
        if self.distribution_started_at is not None and self.distribution_started_at.tzinfo is None:
            raise ValueError("distribution_started_at must include timezone information.")

    @property
    def subscriber_conversion_percentage(self) -> float:
        if self.engaged_views == 0:
            return 0.0
        return (self.subscribers_gained / self.engaged_views) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "published_at": self.published_at.astimezone(timezone.utc).isoformat(),
            "content_format": self.content_format,
            "hook_type": self.hook_type,
            "duration_seconds": self.duration_seconds,
            "viewed_percentage": self.viewed_percentage,
            "engaged_views": self.engaged_views,
            "average_view_duration_seconds": self.average_view_duration_seconds,
            "average_percentage_viewed": self.average_percentage_viewed,
            "subscribers_gained": self.subscribers_gained,
            "subscriber_conversion_percentage": self.subscriber_conversion_percentage,
            "retention_drop_timestamps": list(self.retention_drop_timestamps),
            "experiment_id": self.experiment_id,
            "experiment_variant": self.experiment_variant,
            "distribution_started_at": (
                self.distribution_started_at.astimezone(timezone.utc).isoformat()
                if self.distribution_started_at is not None
                else None
            ),
            "first_3_second_retention_percentage": self.first_3_second_retention_percentage,
            "first_30_second_retention_percentage": self.first_30_second_retention_percentage,
            "impressions_click_through_rate": self.impressions_click_through_rate,
            "comment_question": self.comment_question,
            "comments_count": self.comments_count,
            "title_style": self.title_style,
            "thumbnail_style": self.thumbnail_style,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "YoutubePerformanceRecord":
        return YoutubePerformanceRecord(
            video_id=str(data["video_id"]),
            published_at=datetime.fromisoformat(str(data["published_at"]).replace("Z", "+00:00")),
            content_format=str(data["content_format"]),
            hook_type=str(data["hook_type"]),
            duration_seconds=float(data["duration_seconds"]),
            viewed_percentage=float(data["viewed_percentage"]),
            engaged_views=int(data["engaged_views"]),
            average_view_duration_seconds=float(data["average_view_duration_seconds"]),
            average_percentage_viewed=float(data["average_percentage_viewed"]),
            subscribers_gained=int(data.get("subscribers_gained", 0)),
            retention_drop_timestamps=tuple(
                float(value) for value in data.get("retention_drop_timestamps", [])
            ),
            experiment_id=(str(data["experiment_id"]) if data.get("experiment_id") else None),
            experiment_variant=(
                str(data["experiment_variant"]) if data.get("experiment_variant") else None
            ),
            distribution_started_at=(
                datetime.fromisoformat(
                    str(data["distribution_started_at"]).replace("Z", "+00:00")
                )
                if data.get("distribution_started_at")
                else None
            ),
            first_3_second_retention_percentage=(
                float(data["first_3_second_retention_percentage"])
                if data.get("first_3_second_retention_percentage") is not None
                else None
            ),
            first_30_second_retention_percentage=(
                float(data["first_30_second_retention_percentage"])
                if data.get("first_30_second_retention_percentage") is not None
                else None
            ),
            impressions_click_through_rate=(
                float(data["impressions_click_through_rate"])
                if data.get("impressions_click_through_rate") is not None
                else None
            ),
            comment_question=(
                str(data["comment_question"]) if data.get("comment_question") else None
            ),
            comments_count=int(data.get("comments_count", 0)),
            title_style=(str(data["title_style"]) if data.get("title_style") else None),
            thumbnail_style=(
                str(data["thumbnail_style"]) if data.get("thumbnail_style") else None
            ),
        )


@dataclass(frozen=True)
class PerformanceLearningReport:
    video_id: str
    comparison_scope: str
    baseline_sample_size: int
    baseline: dict[str, float]
    deltas: dict[str, float]
    retention_drop_timestamps: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "comparison_scope": self.comparison_scope,
            "baseline_sample_size": self.baseline_sample_size,
            "baseline": self.baseline,
            "deltas": self.deltas,
            "retention_drop_timestamps": list(self.retention_drop_timestamps),
            "note": "Deltas compare only with this channel's prior matching Shorts.",
        }


@dataclass(frozen=True)
class PerformanceGuidance:
    """Channel-specific production guidance derived from prior publications."""

    content_format: str
    sample_size: int
    preferred_hook_type: str | None
    recommended_pattern_interval_seconds: int
    common_drop_timestamp_seconds: float | None
    successful_comment_question: str | None
    average_first_3_second_retention: float | None
    average_first_30_second_retention: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_format": self.content_format,
            "sample_size": self.sample_size,
            "preferred_hook_type": self.preferred_hook_type,
            "recommended_pattern_interval_seconds": self.recommended_pattern_interval_seconds,
            "common_drop_timestamp_seconds": self.common_drop_timestamp_seconds,
            "successful_comment_question": self.successful_comment_question,
            "average_first_3_second_retention": self.average_first_3_second_retention,
            "average_first_30_second_retention": self.average_first_30_second_retention,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "PerformanceGuidance":
        return PerformanceGuidance(
            content_format=str(data["content_format"]),
            sample_size=int(data["sample_size"]),
            preferred_hook_type=(
                str(data["preferred_hook_type"])
                if data.get("preferred_hook_type")
                else None
            ),
            recommended_pattern_interval_seconds=int(
                data["recommended_pattern_interval_seconds"]
            ),
            common_drop_timestamp_seconds=(
                float(data["common_drop_timestamp_seconds"])
                if data.get("common_drop_timestamp_seconds") is not None
                else None
            ),
            successful_comment_question=(
                str(data["successful_comment_question"])
                if data.get("successful_comment_question")
                else None
            ),
            average_first_3_second_retention=(
                float(data["average_first_3_second_retention"])
                if data.get("average_first_3_second_retention") is not None
                else None
            ),
            average_first_30_second_retention=(
                float(data["average_first_30_second_retention"])
                if data.get("average_first_30_second_retention") is not None
                else None
            ),
        )
