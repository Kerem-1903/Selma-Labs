from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.application.services.hook_variant_scoring_service import (
    HookVariantScoringService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank source-grounded opening hooks while changing only the hook."
    )
    parser.add_argument("--topic", required=True)
    parser.add_argument(
        "--variant",
        action="append",
        required=True,
        help="Hook candidate; pass at least twice.",
    )
    parser.add_argument("--control-index", type=int, default=0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    experiment = HookVariantScoringService().prepare_experiment(
        topic=args.topic,
        variants=args.variant,
        control_index=args.control_index,
    )
    print(json.dumps(experiment.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
