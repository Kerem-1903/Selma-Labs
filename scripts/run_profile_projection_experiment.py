"""Does a profile view rotate, or does it copy its same-wing reference?

Measured on the shipped packs: `PROFILE_RIGHT` agrees with
`THREE_QUARTER_RIGHT` at silhouette IoU 0.973 and `PROFILE_LEFT` with
`THREE_QUARTER_LEFT` at 0.918, while every cross-view pair sits at 0.59-0.62.
Two views of the same body always share some silhouette, so the baseline
matters: the size of that gap is the defect. The instruction is not the
problem -- it already asks for a strict side profile and the negatives already
exclude `three-quarter view` -- so the two candidate levers are the reference
set and the identity window.

Variants, all at the same seed so only the lever differs:

  A  FRONT only                    -- nothing whose pose can be copied
  B  FRONT + same-wing three-quarter, identity_end_at 0.35
                                   -- release the reference early, let the text
                                      instruction drive the rotation
  C  FRONT + same-wing three-quarter, identity_end_at 0.65
                                   -- production settings, the in-run control

Success is a silhouette IoU against the same-wing three-quarter that falls
towards the cross-view baseline. Identity is watched at the same time: a
profile that rotates but stops being Akira is not an improvement, so palette
distance and subject framing are measured against the canonical source with
the same drift service the pack report uses.

Nothing is written into a pack. Output goes to a diagnostics directory.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib

from PIL import Image

from config.provider_registry import get_keyframe_generation_provider
from config.settings import get_settings
from core.application.services.character_identity_prompt_service import (
    CharacterIdentityPromptService,
    edit_canvas_for,
)
from core.application.services.character_turnaround_drift_service import (
    CharacterTurnaroundDriftService,
)
from core.application.services.character_view_pack_asset_service import (
    CharacterViewPackAssetService,
)
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import CharacterCanonicalApproval
from core.domain.value_objects.generation_capability import GenerationCapability
from infrastructure.storage.local_fs_storage import LocalFsStorage
from scripts.turnaround_silhouette import (
    compare_paths,
    normalized_silhouette,
    silhouette_iou,
    subject_mask,
)

#: The view whose pose each profile is supposed to depart from.
SAME_WING: dict[str, str] = {
    "PROFILE_LEFT": "THREE_QUARTER_LEFT",
    "PROFILE_RIGHT": "THREE_QUARTER_RIGHT",
}

#: Reference sets and identity windows each variant is rendered with.
VARIANTS: dict[str, dict[str, object]] = {
    "A": {"references": "front", "identity_end_at": 0.65},
    "B": {"references": "wing", "identity_end_at": 0.35},
    "C": {"references": "wing", "identity_end_at": 0.65},
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", required=True, type=pathlib.Path)
    parser.add_argument("--approval", required=True, type=pathlib.Path)
    parser.add_argument(
        "--pack-root",
        type=pathlib.Path,
        help="Pack directory holding view-pack.json; needed for the same-wing "
        "reference and for the IoU baseline",
    )
    parser.add_argument(
        "--view",
        action="append",
        dest="views",
        help="Profile view to render; repeat. Defaults to both profiles.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        dest="variants",
        choices=sorted(VARIANTS),
        help="Variant to render; repeat. Defaults to all three.",
    )
    parser.add_argument("--seed", type=int, default=424242)
    parser.add_argument(
        "--out", type=pathlib.Path, default=pathlib.Path("output/diagnostics/profile-projection")
    )
    return parser.parse_args()


async def render(
    *,
    generator,
    prompt_service: CharacterIdentityPromptService,
    brief: CharacterCreationBrief,
    approval: CharacterCanonicalApproval,
    storage: LocalFsStorage,
    pack_dir: pathlib.Path,
    view: str,
    variant: str,
    seed: int,
    canvas: tuple[int, int],
    out_dir: pathlib.Path,
) -> dict[str, object]:
    pack = json.loads((pack_dir / "view-pack.json").read_text(encoding="utf-8"))
    by_view = {draft["view"]: draft for draft in pack["views"]}
    wing_view = SAME_WING[view]
    wing = by_view[wing_view]
    wing_bytes = await storage.load(wing["storage_key"])

    references = [
        (
            "FRONT",
            approval.canonical_storage_key,
            approval.canonical_content_hash,
            1.0,
        )
    ]
    if VARIANTS[variant]["references"] == "wing":
        references.append((wing_view, wing["storage_key"], wing["content_hash"], 1.0))

    request = prompt_service.build_reference_request(
        brief,
        view=view,
        direction="left" if view.endswith("LEFT") else "right",
        seed=seed,
        references=tuple(references),
        canvas=canvas,
    )
    # The identity window is a field of the request's visual contract, so the
    # lever is applied to the built request rather than to the prompt text.
    payload = request.to_dict()
    payload["visual_constraints"]["identity_end_at"] = VARIANTS[variant][
        "identity_end_at"
    ]
    request = type(request).from_dict(payload)

    generated = await generator.generate_keyframe(request)
    image_bytes, width, height = CharacterViewPackAssetService.normalized_png(
        generated.image_bytes
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{view.casefold()}_{variant}_seed{seed}.png"
    target.write_bytes(image_bytes)

    # Keep the same-wing reference next to the render so the comparison is
    # reproducible without the pack.
    wing_path = out_dir / f"{view.casefold()}_reference_{wing_view.casefold()}.png"
    if not wing_path.exists():
        wing_path.write_bytes(wing_bytes)

    return {
        "view": view,
        "variant": variant,
        "seed": seed,
        "identity_end_at": VARIANTS[variant]["identity_end_at"],
        "references": [item[0] for item in references],
        "image": str(target),
        "width": width,
        "height": height,
        "sha256": sha256(image_bytes),
        "generation": dict(generated.metadata),
    }


def measure(record: dict[str, object], *, source_path: pathlib.Path) -> None:
    """Fill in the pose and identity numbers for one render."""
    image = Image.open(record["image"])
    mask = subject_mask(image)
    silhouette = normalized_silhouette(mask)
    wing_path = pathlib.Path(record["image"]).parent / (
        f"{record['view'].casefold()}_reference_{SAME_WING[record['view']].casefold()}.png"
    )
    wing_silhouette = normalized_silhouette(subject_mask(Image.open(wing_path)))
    record["iou_vs_same_wing"] = silhouette_iou(silhouette, wing_silhouette)
    record["iou_vs_front"] = compare_paths(record["image"], source_path)


def main() -> None:
    args = parse_args()
    views = tuple(view.upper() for view in (args.views or sorted(SAME_WING)))
    variants = tuple(args.variants or sorted(VARIANTS))
    unknown = [view for view in views if view not in SAME_WING]
    if unknown:
        raise SystemExit(f"Only profile views rotate here; refusing: {unknown}")

    brief = CharacterCreationBrief.from_dict(
        json.loads(args.brief.read_text(encoding="utf-8"))
    )
    approval = CharacterCanonicalApproval.from_dict(
        json.loads(args.approval.read_text(encoding="utf-8"))
    )
    settings = get_settings()
    storage = LocalFsStorage(settings.keyframe_storage_root_dir)
    generator = get_keyframe_generation_provider(
        settings,
        capability=GenerationCapability.CHARACTER_TURNAROUND,
        storage=storage,
    )
    prompt_service = CharacterIdentityPromptService()

    async def run() -> list[dict[str, object]]:
        canonical, width, height = CharacterViewPackAssetService.normalized_png(
            await storage.load(approval.canonical_storage_key)
        )
        canvas = edit_canvas_for(width, height)
        source_path = args.out / "canonical_source.png"
        args.out.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(canonical)
        records: list[dict[str, object]] = []
        for view in views:
            for variant in variants:
                record = await render(
                    generator=generator,
                    prompt_service=prompt_service,
                    brief=brief,
                    approval=approval,
                    storage=storage,
                    pack_dir=args.pack_root,
                    view=view,
                    variant=variant,
                    seed=args.seed,
                    canvas=canvas,
                    out_dir=args.out,
                )
                records.append(record)
        return records

    records = asyncio.run(run())

    # The drift service measures the identity side with the character's own
    # signature-mark colour, exactly as the pack report does.
    mark = next(
        (item for item in brief.signature_marks if str(item.colour).strip()), None
    )
    drift = CharacterTurnaroundDriftService(
        accent_colour=mark.colour if mark is not None else "",
        mark_side=(
            mark.character_side
            if mark is not None and mark.character_side in {"left", "right"}
            else ""
        ),
    )
    source_bytes = (args.out / "canonical_source.png").read_bytes()
    for record in records:
        measure(record, source_path=args.out / "canonical_source.png")
        report = drift.evaluate(
            source_bytes=source_bytes,
            views={record["view"]: pathlib.Path(record["image"]).read_bytes()},
        )["views"][0]
        record["drift"] = {
            "status": report["status"],
            "reasons": list(report["reasons"]),
            **{name: float(value) for name, value in report["metrics"].items()},
        }

    manifest = {
        "schema_version": 1,
        "character_id": brief.character_id,
        "character_version": approval.character_version,
        "brief_hash": brief.content_hash,
        "seed": args.seed,
        "variants": VARIANTS,
        "views": list(views),
        "renders": records,
    }
    (args.out / "experiment.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"seed {args.seed} -- ayni kanat referansi ve kimlik penceresi kaldiraclari")
    for view in views:
        print(f"\n{view}  (kopyalamamasi gereken kare: {SAME_WING[view]})")
        for record in [item for item in records if item["view"] == view]:
            drift_values = record["drift"]
            print(
                f"  {record['variant']}: IoU vs ayni kanat {record['iou_vs_same_wing']:.3f}"
                f" | IoU vs on {record['iou_vs_front']:.3f}"
                f" | palette {drift_values['palette_distance']:.3f}"
                f" | genislik {drift_values['subject_width_ratio_delta']:+.3f}"
                f" | yukseklik {drift_values['subject_height_ratio_delta']:+.3f}"
            )
    print(f"\nwrote {args.out / 'experiment.json'}")


if __name__ == "__main__":
    main()
