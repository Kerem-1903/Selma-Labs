#!/usr/bin/env python3
"""
Sprint 3 manual test entrypoint — Visual Asset Discovery.

Usage:
    python scripts/search_assets.py "Titanic ship"
    python scripts/search_assets.py "Titanic ship" --max-results 5
    python scripts/search_assets.py "Titanic ship" --json

This script is the Sprint 3 composition root: the one place that wires the
concrete PexelsProvider and the concrete storage backend into
VideoSearchService. VideoSearchService itself never knows which provider or
storage backend it is using.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.provider_registry import get_video_source_provider  # noqa: E402
from config.settings import get_settings  # noqa: E402
from core.application.services.video_search_service import VideoSearchService  # noqa: E402
from core.domain.exceptions import SelmaError  # noqa: E402
from infrastructure.storage.local_fs_storage import LocalFsStorage  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search for and download visual assets for a query."
    )
    parser.add_argument("query", type=str, help="Search query, e.g. 'Titanic ship'")
    parser.add_argument(
        "--max-results", type=int, default=None,
        help="Maximum number of assets to fetch (1-80). Defaults to config value.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print results as JSON instead of the human-readable summary.",
    )
    args = parser.parse_args()

    settings = get_settings()
    max_results = args.max_results or settings.default_video_max_results
    storage = LocalFsStorage(root_dir=settings.storage_root_dir)

    try:
        provider = get_video_source_provider(settings)
        service = VideoSearchService(provider=provider, storage=storage)
        assets = await service.discover(query=args.query, max_results=max_results)
    except SelmaError as exc:
        print(f"Video search failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        import json
        print(json.dumps([asset.to_dict() for asset in assets], indent=2))
        return

    print("=" * 60)
    print(f"Query:        {args.query}")
    print(f"Assets found: {len(assets)}")
    print("=" * 60)
    for asset in assets:
        print(f"ID:          {asset.id}")
        print(f"Provider:    {asset.provider}")
        print(f"Dimensions:  {asset.width}x{asset.height} @ {asset.fps} fps")
        print(f"Duration:    {asset.duration_seconds}s")
        print(f"Tags:        {', '.join(asset.tags)}")
        print(f"Attribution: {asset.attribution}")
        print(f"License:     {asset.license}")
        print(f"Local path:  {asset.local_path}")
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
