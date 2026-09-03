from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.application.services.character_lora_dataset_service import (
    CharacterLoraDatasetService,
)
from core.domain.entities.character_bible import CharacterBible


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and validate a versioned SELMA character LoRA dataset."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--trigger-token", required=True)
    parser.add_argument(
        "--character-bible",
        type=Path,
        help="Character Bible JSON used for identity-specific captions",
    )
    parser.add_argument("--minimum-train", type=int, default=20)
    parser.add_argument("--minimum-holdout", type=int, default=3)
    args = parser.parse_args()

    character_bible = None
    if args.character_bible:
        payload = json.loads(args.character_bible.read_text(encoding="utf-8"))
        character_bible = CharacterBible.from_dict(
            payload.get("character_bible", payload)
        )
    service = CharacterLoraDatasetService(
        required_training_images=args.minimum_train,
        required_holdout_images=args.minimum_holdout,
    )
    report = service.build(
        source_dir=args.source,
        output_dir=args.output,
        character_id=args.character_id,
        trigger_token=args.trigger_token,
        character_bible=character_bible,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.is_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
