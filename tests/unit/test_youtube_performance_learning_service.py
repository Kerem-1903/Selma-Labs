from datetime import datetime, timezone
import asyncio
import json

import pytest

from core.application.services.youtube_performance_learning_service import (
    YoutubePerformanceLearningService,
)
from core.domain.value_objects.youtube_performance import YoutubePerformanceRecord
from infrastructure.repositories.sqlite_youtube_performance_repository import SQLiteYoutubePerformanceRepository
from core.domain.exceptions import PerformanceDataError


def _record(
    video_id: str,
    viewed: float,
    *,
    hook_type: str = "question",
    retention_drop_timestamps: tuple[float, ...] = (4.0, 18.0),
    comment_question: str | None = None,
    comments_count: int = 0,
):
    return YoutubePerformanceRecord(
        video_id=video_id,
        published_at=datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc),
        content_format="single_fact",
        hook_type=hook_type,
        duration_seconds=40.0,
        viewed_percentage=viewed,
        engaged_views=1_000,
        average_view_duration_seconds=30.0,
        average_percentage_viewed=75.0,
        subscribers_gained=10,
        retention_drop_timestamps=retention_drop_timestamps,
        first_3_second_retention_percentage=82.0,
        first_30_second_retention_percentage=64.0,
        impressions_click_through_rate=6.5,
        comment_question=comment_question,
        comments_count=comments_count,
    )


@pytest.mark.asyncio
async def test_learning_loop_compares_only_matching_channel_history(tmp_path):
    repository = SQLiteYoutubePerformanceRepository(":memory:")
    service = YoutubePerformanceLearningService(repository)
    await service.record_and_compare(_record("control", 60.0))
    await service.record_and_compare(_record("other-hook", 90.0, hook_type="contrast"))

    report = await service.record_and_compare(_record("candidate", 72.0))

    assert report.comparison_scope == "content_format_and_hook_type"
    assert report.baseline_sample_size == 1
    assert report.baseline["viewed_percentage"] == 60.0
    assert report.deltas["viewed_percentage"] == 12.0
    assert report.baseline["first_3_second_retention_percentage"] == 82.0
    assert report.baseline["impressions_click_through_rate"] == 6.5
    assert report.retention_drop_timestamps == (4.0, 18.0)


@pytest.mark.asyncio
async def test_repository_updates_same_video_without_duplicate(tmp_path):
    repository = SQLiteYoutubePerformanceRepository(":memory:")
    await repository.save(_record("same", 50.0))
    await repository.save(_record("same", 70.0))

    records = await repository.list_records()

    assert len(records) == 1
    assert records[0].viewed_percentage == 70.0


@pytest.mark.asyncio
async def test_repository_serializes_concurrent_writers_across_instances(tmp_path):
    path = ":memory:"
    master = SQLiteYoutubePerformanceRepository(path)
    repositories = [SQLiteYoutubePerformanceRepository(master.db_path) for _ in range(12)]

    await asyncio.gather(*(
        repository.save(_record(f"video-{index}", 50.0 + index))
        for index, repository in enumerate(repositories)
    ))

    records = await SQLiteYoutubePerformanceRepository(master.db_path).list_records()
    assert len(records) == 12
    assert {record.video_id for record in records} == {
        f"video-{index}" for index in range(12)
    }


@pytest.mark.asyncio
async def test_build_guidance_returns_channel_specific_production_inputs(tmp_path):
    repository = SQLiteYoutubePerformanceRepository(":memory:")
    service = YoutubePerformanceLearningService(repository)
    for index in range(10):
        await repository.save(
            _record(
                f"video-{index}",
                78.0 if index < 7 else 55.0,
                hook_type="question" if index < 7 else "contrast",
                retention_drop_timestamps=(22.0,),
                comment_question=(
                    "Sence en şaşırtıcı bölüm hangisiydi?" if index == 4 else None
                ),
                comments_count=80 if index == 4 else 0,
            )
        )

    guidance = await service.build_guidance("single_fact")

    assert guidance.sample_size == 10
    assert guidance.preferred_hook_type == "question"
    assert guidance.common_drop_timestamp_seconds == 20.0
    assert guidance.recommended_pattern_interval_seconds == 20
    assert guidance.successful_comment_question == "Sence en şaşırtıcı bölüm hangisiydi?"
    assert guidance.average_first_3_second_retention == 82.0
