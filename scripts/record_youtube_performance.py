from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.application.services.youtube_performance_learning_service import (
    YoutubePerformanceLearningService,
)
from core.domain.value_objects.youtube_performance import YoutubePerformanceRecord
from infrastructure.repositories.local_json_youtube_performance_repository import (
    LocalJsonYoutubePerformanceRepository,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record one published Short and compare it with channel history."
    )
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--published-at", required=True, help="Timezone-aware ISO timestamp.")
    parser.add_argument("--content-format", default="single_fact")
    parser.add_argument("--hook-type", required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--viewed-percentage", type=float, required=True)
    parser.add_argument("--engaged-views", type=int, required=True)
    parser.add_argument("--average-view-duration-seconds", type=float, required=True)
    parser.add_argument("--average-percentage-viewed", type=float, required=True)
    parser.add_argument("--subscribers-gained", type=int, default=0)
    parser.add_argument("--retention-drop", action="append", type=float, default=[])
    parser.add_argument("--experiment-id")
    parser.add_argument("--experiment-variant")
    parser.add_argument("--distribution-started-at", help="Timezone-aware ISO timestamp.")
    parser.add_argument("--first-3-second-retention-percentage", type=float)
    parser.add_argument("--first-30-second-retention-percentage", type=float)
    parser.add_argument("--impressions-click-through-rate", type=float)
    parser.add_argument("--comment-question")
    parser.add_argument("--comments-count", type=int, default=0)
    parser.add_argument("--title-style")
    parser.add_argument("--thumbnail-style")
    parser.add_argument("--store", default="data/youtube_performance.json")
    return parser


async def run(args: argparse.Namespace) -> dict[str, object]:
    repository = LocalJsonYoutubePerformanceRepository(args.store)
    service = YoutubePerformanceLearningService(repository)
    record = YoutubePerformanceRecord(
        video_id=args.video_id,
        published_at=datetime.fromisoformat(args.published_at.replace("Z", "+00:00")),
        content_format=args.content_format,
        hook_type=args.hook_type,
        duration_seconds=args.duration_seconds,
        viewed_percentage=args.viewed_percentage,
        engaged_views=args.engaged_views,
        average_view_duration_seconds=args.average_view_duration_seconds,
        average_percentage_viewed=args.average_percentage_viewed,
        subscribers_gained=args.subscribers_gained,
        retention_drop_timestamps=tuple(args.retention_drop),
        experiment_id=args.experiment_id,
        experiment_variant=args.experiment_variant,
        distribution_started_at=(
            datetime.fromisoformat(args.distribution_started_at.replace("Z", "+00:00"))
            if args.distribution_started_at
            else None
        ),
        first_3_second_retention_percentage=(
            args.first_3_second_retention_percentage
        ),
        first_30_second_retention_percentage=(
            args.first_30_second_retention_percentage
        ),
        impressions_click_through_rate=args.impressions_click_through_rate,
        comment_question=args.comment_question,
        comments_count=args.comments_count,
        title_style=args.title_style,
        thumbnail_style=args.thumbnail_style,
    )
    return (await service.record_and_compare(record)).to_dict()


def main() -> None:
    args = build_parser().parse_args()
    print(json.dumps(asyncio.run(run(args)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
