from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from io import BytesIO
from pathlib import Path, PurePosixPath

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.application.services.character_reference_asset_service import (
    CharacterReferenceAssetService,
)
from core.domain.entities.character_bible import CharacterBible
from core.domain.exceptions import CharacterBibleNotFoundError
from core.domain.services.character_bible_validation_service import (
    CharacterBibleValidationService,
)
from core.domain.value_objects.character_identity import IdentityConstraints, ReferenceView
from core.domain.value_objects.style_profile import StyleProfile
from infrastructure.repositories.local_json_character_bible_repository import (
    LocalJsonCharacterBibleRepository,
)
from infrastructure.storage.local_fs_storage import LocalFsStorage


EXPECTED_SHEET_SIZE = (1717, 916)
AKIRA_VIEW_CROPS: dict[ReferenceView, tuple[int, int, int, int]] = {
    ReferenceView.FRONT: (2, 2, 381, 914),
    ReferenceView.THREE_QUARTER_LEFT: (382, 2, 701, 914),
    ReferenceView.PROFILE_LEFT: (702, 2, 975, 914),
    ReferenceView.BACK: (976, 2, 1315, 914),
    ReferenceView.FACE_CLOSEUP: (1316, 2, 1715, 663),
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Split Akira's approved multi-view sheet and persist the five views "
            "through StoragePort and CharacterBibleRepository."
        )
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=PROJECT_ROOT / "assets",
        help="Local StoragePort root (default: project assets directory).",
    )
    parser.add_argument(
        "--bible-root",
        type=Path,
        default=PROJECT_ROOT / "assets" / "character_bibles",
        help="Character Bible JSON directory.",
    )
    return parser


def split_reference_sheet(source: Path) -> dict[ReferenceView, bytes]:
    if not source.is_file():
        raise FileNotFoundError(f"Akira reference sheet was not found: {source}")

    with Image.open(source) as image:
        image.load()
        if image.size != EXPECTED_SHEET_SIZE:
            raise ValueError(
                "Akira reference sheet has unexpected dimensions: "
                f"expected {EXPECTED_SHEET_SIZE[0]}x{EXPECTED_SHEET_SIZE[1]}, "
                f"found {image.width}x{image.height}."
            )

        rgb = image.convert("RGB")
        references: dict[ReferenceView, bytes] = {}
        for view, crop_box in AKIRA_VIEW_CROPS.items():
            output = BytesIO()
            rgb.crop(crop_box).save(output, format="PNG", optimize=True)
            references[view] = output.getvalue()
        return references


def new_akira_bible() -> CharacterBible:
    return CharacterBible(
        character_id="akira",
        identity_constraints=IdentityConstraints(
            eye_color="amber-brown",
            hair="long black hair with one controlled red front streak",
            facial_geometry="angular anime face with narrow jaw and straight nose",
            body_proportions="athletic adult woman",
            silhouette="lean swordswoman in a cropped field jacket and tall boots",
            immutable_marks=[
                "single red hair streak on the left-front section",
                "amber eyes",
            ],
        ),
        style_profile=StyleProfile(
            base_style="clean cinematic anime character design",
            color_palette=["charcoal", "black", "muted gray", "deep red", "amber"],
            negative_prompts=[
                "identity drift",
                "different outfit",
                "red ribbon",
                "red energy trail",
                "extra weapon",
            ],
        ),
    )


def _is_portable_storage_key(key: str) -> bool:
    normalized = key.replace("\\", "/")
    path = PurePosixPath(normalized)
    return bool(normalized) and not path.is_absolute() and ":" not in normalized and ".." not in path.parts


async def import_reference_pack(
    source: Path,
    storage_root: Path,
    bible_root: Path,
) -> CharacterBible:
    references = split_reference_sheet(source)
    storage = LocalFsStorage(str(storage_root))
    repository = LocalJsonCharacterBibleRepository(bible_root)
    assets = CharacterReferenceAssetService(storage)

    try:
        bible = await repository.load("akira")
    except CharacterBibleNotFoundError:
        bible = new_akira_bible()

    for view in CharacterBibleValidationService.DEFAULT_REQUIRED_VIEWS:
        data = references[view]
        existing = bible.reference_pack.get(view)
        digest = hashlib.sha256(data).hexdigest()
        if existing is not None and existing.content_hash == digest:
            continue
        await assets.save_reference(bible, view, data, "image/png")

    report = CharacterBibleValidationService().validate(bible)
    if not report.is_complete:
        missing = ", ".join(view.value for view in report.missing_views) or "none"
        invalid = "; ".join(item.reason for item in report.invalid_references) or "none"
        raise ValueError(
            f"Akira reference pack is incomplete (missing: {missing}; invalid: {invalid})."
        )

    await repository.save(bible)
    restored = await repository.load("akira")
    restored_report = CharacterBibleValidationService().validate(restored)
    if not restored_report.is_complete:
        raise RuntimeError("Persisted Akira Character Bible failed multi-view validation.")

    for view in CharacterBibleValidationService.DEFAULT_REQUIRED_VIEWS:
        reference = restored.reference_pack[view]
        if not _is_portable_storage_key(reference.storage_key):
            raise RuntimeError(f"Non-portable storage key persisted for {view.value}.")
        if await assets.load_reference(reference) != references[view]:
            raise RuntimeError(f"Stored bytes failed round-trip verification for {view.value}.")
    return restored


async def _run(args: argparse.Namespace) -> None:
    bible = await import_reference_pack(
        source=args.source.resolve(),
        storage_root=args.storage_root.resolve(),
        bible_root=args.bible_root.resolve(),
    )
    print(f"Akira Character Bible: {args.bible_root.resolve() / 'akira.json'}")
    for view in CharacterBibleValidationService.DEFAULT_REQUIRED_VIEWS:
        reference = bible.reference_pack[view]
        print(
            f"{view.value}: {reference.storage_key} "
            f"(asset_id={reference.asset_id}, revision={reference.revision}, "
            f"sha256={reference.content_hash})"
        )


def main() -> None:
    args = build_arg_parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
