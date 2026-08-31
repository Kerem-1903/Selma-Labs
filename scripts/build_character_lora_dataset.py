from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.application.services.character_lora_dataset_service import (  # noqa: E402
    CharacterLoraDatasetService,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and validate a versioned SELMA character LoRA dataset."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--trigger-token", required=True)
    parser.add_argument("--minimum-train", type=int, default=20)
    parser.add_argument("--minimum-holdout", type=int, default=3)
    args = parser.parse_args()

    service = CharacterLoraDatasetService(
        required_training_images=args.minimum_train,
        required_holdout_images=args.minimum_holdout,
    )
    report = service.build(
        source_dir=args.source,
        output_dir=args.output,
        character_id=args.character_id,
        trigger_token=args.trigger_token,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
