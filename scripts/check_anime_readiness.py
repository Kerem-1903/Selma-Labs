from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.application.services.anime_production_readiness_service import (
    ANIMATION,
    VISUAL,
    AnimeProductionReadinessService,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check anime visual or animation production readiness."
    )
    parser.add_argument("--stage", choices=(VISUAL, ANIMATION), required=True)
    parser.add_argument("--series", default="config/series/selma-anime-v1.json")
    parser.add_argument("--episode-root")
    parser.add_argument("--requirements")
    parser.add_argument("--full-model-hash", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    arguments = parser.parse_args()
    report = AnimeProductionReadinessService(PROJECT_ROOT).evaluate(
        arguments.stage,
        series_project=arguments.series,
        episode_root=arguments.episode_root,
        requirements_path=arguments.requirements,
        full_model_hash=arguments.full_model_hash,
    )
    if arguments.as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"SELMA anime readiness: {arguments.stage}")
        for check in report.checks:
            print(f"[{check.status}] {check.name}: {check.details}")
            if check.remediation:
                print(f"       Fix: {check.remediation}")
        print("READY" if report.ready else "NOT READY")
    raise SystemExit(0 if report.ready else 1)


if __name__ == "__main__":
    main()
