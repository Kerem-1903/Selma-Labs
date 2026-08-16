from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from core.application.services.system_health_service import SystemHealthService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether the local SELMA factory is ready before spending API quota."
    )
    parser.add_argument(
        "--profile",
        choices=("factory", "audio", "trends"),
        default="factory",
    )
    parser.add_argument("--run-directory", default=".selma_runs")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = SystemHealthService(
        get_settings(),
        project_root=PROJECT_ROOT,
    ).evaluate(profile=args.profile, run_directory=args.run_directory)
    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"SELMA system health — {args.profile}")
        for check in report.checks:
            print(f"[{check.status}] {check.name}: {check.details}")
            if check.remediation:
                print(f"       Fix: {check.remediation}")
        print("READY" if report.ready else "NOT READY")
    raise SystemExit(0 if report.ready else 1)


if __name__ == "__main__":
    main()
