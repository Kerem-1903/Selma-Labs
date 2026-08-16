"""Compare each published Short with this channel's own rolling baseline."""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import fmean

from core.domain.ports.youtube_performance_repository_port import (
    YoutubePerformanceRepositoryPort,
)
from core.domain.value_objects.youtube_performance import (
    PerformanceLearningReport,
    PerformanceGuidance,
    YoutubePerformanceRecord,
)


class YoutubePerformanceLearningService:
    def __init__(
        self,
        repository: YoutubePerformanceRepositoryPort,
        *,
        rolling_window: int = 20,
    ) -> None:
        if rolling_window <= 0:
            raise ValueError("rolling_window must be greater than zero.")
        self._repository = repository
        self._rolling_window = rolling_window

    async def record_and_compare(
        self,
        record: YoutubePerformanceRecord,
    ) -> PerformanceLearningReport:
        existing = tuple(
            item for item in await self._repository.list_records()
            if item.video_id != record.video_id
        )
        exact = [
            item for item in existing
            if item.content_format == record.content_format and item.hook_type == record.hook_type
        ]
        if exact:
            cohort = exact[-self._rolling_window:]
            scope = "content_format_and_hook_type"
        else:
            cohort = [
                item for item in existing if item.content_format == record.content_format
            ][-self._rolling_window:]
            scope = "content_format"

        metric_values = {
            "viewed_percentage": record.viewed_percentage,
            "average_view_duration_seconds": record.average_view_duration_seconds,
            "average_percentage_viewed": record.average_percentage_viewed,
            "subscriber_conversion_percentage": record.subscriber_conversion_percentage,
        }
        metric_values.update({
            name: value
            for name, value in (
                (
                    "first_3_second_retention_percentage",
                    record.first_3_second_retention_percentage,
                ),
                (
                    "first_30_second_retention_percentage",
                    record.first_30_second_retention_percentage,
                ),
                (
                    "impressions_click_through_rate",
                    record.impressions_click_through_rate,
                ),
            )
            if value is not None
        })
        baseline: dict[str, float] = {}
        for name in metric_values:
            values = [
                value
                for item in cohort
                if (value := self._metric(item, name)) is not None
            ]
            if values:
                baseline[name] = round(fmean(values), 4)
        deltas = {
            name: round(value - baseline[name], 4)
            for name, value in metric_values.items()
            if name in baseline
        }
        await self._repository.save(record)
        return PerformanceLearningReport(
            video_id=record.video_id,
            comparison_scope=scope,
            baseline_sample_size=len(cohort),
            baseline=baseline,
            deltas=deltas,
            retention_drop_timestamps=record.retention_drop_timestamps,
        )

    async def build_guidance(self, content_format: str) -> PerformanceGuidance:
        """Turn this channel's recent matching records into production inputs."""
        records = [
            item for item in await self._repository.list_records()
            if item.content_format == content_format
        ][-self._rolling_window:]
        if not records:
            return PerformanceGuidance(
                content_format=content_format,
                sample_size=0,
                preferred_hook_type=None,
                recommended_pattern_interval_seconds=25,
                common_drop_timestamp_seconds=None,
                successful_comment_question=None,
                average_first_3_second_retention=None,
                average_first_30_second_retention=None,
            )

        hooks: dict[str, list[YoutubePerformanceRecord]] = defaultdict(list)
        for record in records:
            hooks[record.hook_type].append(record)
        preferred_hook_type = max(
            sorted(hooks),
            key=lambda hook_type: (
                fmean(item.viewed_percentage for item in hooks[hook_type]),
                fmean(item.average_percentage_viewed for item in hooks[hook_type]),
            ),
        )

        drop_buckets = Counter(
            round(timestamp / 5) * 5
            for record in records
            for timestamp in record.retention_drop_timestamps
        )
        common_drop = (
            min(
                (
                    (bucket, count)
                    for bucket, count in drop_buckets.items()
                    if count == max(drop_buckets.values())
                ),
                key=lambda item: item[0],
            )[0]
            if drop_buckets
            else None
        )
        interval = (
            min(30, max(20, int(common_drop) - 2))
            if common_drop is not None
            else 25
        )

        question_records = [
            record for record in records
            if record.comment_question and record.engaged_views > 0
        ]
        best_question = (
            max(
                question_records,
                key=lambda item: (
                    item.comments_count / item.engaged_views,
                    item.comments_count,
                ),
            ).comment_question
            if question_records
            else None
        )
        first_3 = [
            item.first_3_second_retention_percentage
            for item in records
            if item.first_3_second_retention_percentage is not None
        ]
        first_30 = [
            item.first_30_second_retention_percentage
            for item in records
            if item.first_30_second_retention_percentage is not None
        ]
        return PerformanceGuidance(
            content_format=content_format,
            sample_size=len(records),
            preferred_hook_type=preferred_hook_type,
            recommended_pattern_interval_seconds=interval,
            common_drop_timestamp_seconds=(
                float(common_drop) if common_drop is not None else None
            ),
            successful_comment_question=best_question,
            average_first_3_second_retention=(
                round(fmean(first_3), 4) if first_3 else None
            ),
            average_first_30_second_retention=(
                round(fmean(first_30), 4) if first_30 else None
            ),
        )

    @staticmethod
    def _metric(record: YoutubePerformanceRecord, name: str) -> float | None:
        if name == "subscriber_conversion_percentage":
            return record.subscriber_conversion_percentage
        value = getattr(record, name)
        return float(value) if value is not None else None
