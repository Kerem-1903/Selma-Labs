#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.provider_registry import (
    get_topic_selection_provider,
    get_trend_source_provider,
)
from config.settings import get_settings
from core.application.services.trend_topic_service import TrendTopicService


async def get_trending_topic(settings) -> str:
    """Helper for the Scheduler Bot to fetch a topic directly without CLI args."""
    trend_provider = get_trend_source_provider(settings)
    selection_provider = get_topic_selection_provider(settings)
    service = TrendTopicService(
        trend_provider,
        selection_provider,
        settings.trend_candidate_limit,
    )
    result = await service.select_topic(
        region_code=settings.trend_region_code,
        language=settings.trend_relevance_language,
        category_ids=[
            c.strip() for c in settings.trend_category_ids.split(",") if c.strip()
        ]
        if settings.trend_category_ids
        else None,
        max_results_per_category=settings.trend_max_results_per_category,
    )
    return result.topic

async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Select an original Shorts topic from YouTube trend signals."
    )
    parser.add_argument("--region", default=None)
    parser.add_argument("--language", default="en")
    parser.add_argument("--categories", default=None)
    args = parser.parse_args()

    settings = get_settings()
    category_text = args.categories or settings.trend_category_ids
    service = TrendTopicService(
        source_provider=get_trend_source_provider(settings),
        selection_provider=get_topic_selection_provider(settings),
        candidate_limit=settings.trend_candidate_limit,
    )
    selection = await service.discover(
        region_code=args.region or settings.trend_region_code,
        category_ids=[item.strip() for item in category_text.split(",") if item.strip()],
        max_results_per_category=settings.trend_max_results_per_category,
        language=args.language,
    )
    print(json.dumps(selection.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
