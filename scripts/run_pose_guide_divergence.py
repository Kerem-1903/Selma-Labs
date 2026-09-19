"""Do five pose guides produce five poses?

The pose guides were rebuilt so each view is projected from one shared
yaw-parameterised rig. Measured on the template pixels, the old guides made
`THREE_QUARTER_LEFT` *narrower than* `PROFILE_LEFT` (shoulder band / body
height 0.039 vs 0.047, where a true 45-degree view owes 0.118), so a pose pack
drawn from them could satisfy its QC orientation check and still ship the same
body five times.

This rerenders the five poses a pack already contains -- same seed, same
reference chain, same pose guide, same style lock -- with the corrected guides,
and measures the silhouette IoU matrix on both sides of the change. The old
renders are read from the pack; nothing is written into a pack.

Success is the one number that matters: a same-wing pair (`THREE_QUARTER_*` vs
its `PROFILE_*`) has to fall from the near-duplicate band towards the
cross-view baseline, without the identity drifting away from the pose it
replaces.

Writes into a diagnostics directory only.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib
import shutil
import subprocess

from PIL import Image

from config.provider_registry import get_keyframe_generation_provider
from config.settings import get_settings
from core.application.services.character_identity_prompt_service import (
    CharacterIdentityPromptService,
)
from core.application.services.character_view_pack_asset_service import (
    CharacterViewPackAssetService,
)
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import CharacterCanonicalApproval
from core.domain.value_objects.generation_capability import GenerationCapability
from infrastructure.storage.local_fs_storage import LocalFsStorage
from scripts.turnaround_silhouette import (
    normalized_silhouette,
    silhouette_iou,
    subject_mask,
)

#: Orientation a pose's QC check expects, and the label the reference chain uses.
POSE_MATCH_VIEW: dict[str, str] = {
    "FRONT_NEUTRAL": "FRONT",
    "THREE_QUARTER_LEFT": "THREE_QUARTER_LEFT",
    "PROFILE_LEFT": "PROFILE_LEFT",
    "THREE_QUARTER_RIGHT": "THREE_QUARTER_RIGHT",
    "BACK_FULL_BODY": "BACK",
}

#: Pairs that must stop looking like each other: a three-quarter view and the
#: profile of the same wing are one rotation step apart, not one pose.
SAME_WING: tuple[tuple[str, str], ...] = (
    ("THREE_QUARTER_LEFT", "PROFILE_LEFT"),
    ("THREE_QUARTER_RIGHT", "PROFILE_RIGHT"),
)

#: Free RAM a render needs; the CLI preflight refuses below this and a
#: diagnostic has no business being laxer than production.
MIN_FREE_RAM_GB = 4.0


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def free_ram_gb() -> float:
    import ctypes

    class _MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(_MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return -1.0
    return status.ullAvailPhys / 1024**3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", required=True, type=pathlib.Path)
    parser.add_argument("--approval", required=True, type=pathlib.Path)
    parser.add_argument(
        "--pack-dir",
        required=True,
        type=pathlib.Path,
        help="Directory holding the pack's manifest.json and poses/",
    )
    parser.add_argument(
        "--asset-templates",
        type=pathlib.Path,
        default=pathlib.Path("assets/pose_templates"),
        help="Where the guide files live, for the guide-level measurement",
    )
    parser.add_argument(
        "--old-guide-rev",
        default="HEAD",
        help="Git revision to read the previous guides from; empty to skip",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=pathlib.Path("output/diagnostics/pose-guide-divergence"),
    )
    parser.add_argument(
        "--pose",
        action="append",
        dest="poses",
        help="Limit to these pose ids; defaults to every pose in the pack",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Measure the guides and the pack on disk without rendering",
    )
    return parser.parse_args()


def silhouette_of(path: pathlib.Path):
    with Image.open(path) as image:
        return normalized_silhouette(subject_mask(image))


def matrix(
    silhouettes: dict[str, object], poses: tuple[str, ...]
) -> dict[str, dict[str, float]]:
    return {
        left: {
            right: silhouette_iou(silhouettes[left], silhouettes[right])
            for right in poses
        }
        for left in poses
    }


def palette_of(path: pathlib.Path) -> tuple[float, float, float]:
    """Mean colour of the subject's own pixels, background removed."""
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        mask = subject_mask(rgb)
        pixels = list(rgb.getdata())
    total = [0.0, 0.0, 0.0]
    count = 0
    for index, keep in enumerate(mask):
        if keep:
            pixel = pixels[index]
            for channel in range(3):
                total[channel] += pixel[channel]
            count += 1
    if not count:
        return (0.0, 0.0, 0.0)
    return tuple(round(value / count, 2) for value in total)  # type: ignore[return-value]


def palette_distance(left, right) -> float:
    return sum(abs(a - b) for a, b in zip(left, right)) / 3.0


def framing_of(path: pathlib.Path) -> dict[str, float]:
    """Subject box, so a pose that shrank can be told from one that rotated."""
    with Image.open(path) as image:
        mask = subject_mask(image)
        width, height = image.size
    columns = [
        index % width for index, keep in enumerate(mask) if keep
    ]
    rows = [index // width for index, keep in enumerate(mask) if keep]
    if not columns:
        return {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
    return {
        "left": round(min(columns) / width, 4),
        "right": round(max(columns) / width, 4),
        "top": round(min(rows) / height, 4),
        "bottom": round(max(rows) / height, 4),
    }


def guide_silhouettes(args: argparse.Namespace, packs: dict[str, str], out: pathlib.Path):
    """Current and previous guide pixels, keyed by pose id."""
    current, previous = {}, {}
    for pose_id, storage_key in packs.items():
        name = pathlib.PurePosixPath(storage_key).name
        live = args.asset_templates / name
        if live.is_file():
            current[pose_id] = silhouette_of(live)
            shutil.copyfile(live, out / "guides-new" / f"{pose_id}.png")
        if not args.old_guide_rev:
            continue
        try:
            data = subprocess.run(
                [
                    "git",
                    "show",
                    f"{args.old_guide_rev}:{args.asset_templates.as_posix()}/{name}",
                ],
                check=True,
                capture_output=True,
            ).stdout
        except subprocess.CalledProcessError:
            continue
        target = out / "guides-old" / f"{pose_id}.png"
        target.write_bytes(data)
        previous[pose_id] = silhouette_of(target)
    return current, previous


def report_matrix(
    title: str, values: dict[str, dict[str, float]], poses: tuple[str, ...]
) -> None:
    print(f"\n{title}")
    print("            " + "".join(f"{pose[:11]:>13}" for pose in poses))
    for left in poses:
        cells = "".join(f"{values[left][right]:>13.3f}" for right in poses)
        print(f"{left[:11]:<12}{cells}")
    same = [values[a][b] for a, b in SAME_WING if a in values and b in values[a]]
    cross = [
        values[a][b]
        for a in poses
        for b in poses
        if a != b and (a, b) not in SAME_WING
    ]
    if same:
        print(
            f"  same-wing mean {sum(same) / len(same):.3f}"
            f"  |  other pairs mean {sum(cross) / len(cross):.3f}"
            f"  |  gap {sum(cross) / len(cross) - sum(same) / len(same):+.3f}"
        )


def main() -> None:
    args = parse_args()
    for folder in ("guides-new", "guides-old", "poses-new", "poses-old"):
        (args.out / folder).mkdir(parents=True, exist_ok=True)

    brief = CharacterCreationBrief.from_dict(
        json.loads(args.brief.read_text(encoding="utf-8"))
    )
    approval = CharacterCanonicalApproval.from_dict(
        json.loads(args.approval.read_text(encoding="utf-8"))
    )
    manifest = json.loads(
        (args.pack_dir / "manifest.json").read_text(encoding="utf-8")
    )
    poses = tuple(
        pose["pose_id"]
        for pose in manifest["poses"]
        if not args.poses or pose["pose_id"] in {p.upper() for p in args.poses}
    )
    recorded = {pose["pose_id"]: pose for pose in manifest["poses"]}

    # The pack's own staged copies are what a render consumes, so measuring
    # those is measuring the real input rather than the repository's copy.
    settings = get_settings()
    storage = LocalFsStorage(settings.keyframe_storage_root_dir)
    packs = {
        pose_id: recorded[pose_id]["pose_template_storage_key"] for pose_id in poses
    }
    current_guides, previous_guides = guide_silhouettes(args, packs, args.out)
    guide_records = {
        pose_id: {
            "storage_key": packs[pose_id],
            "sha256": sha256(
                (args.out / "guides-new" / f"{pose_id}.png").read_bytes()
            ),
            "recorded_in_pack": recorded[pose_id]["pose_template_hash"],
        }
        for pose_id in poses
        if (args.out / "guides-new" / f"{pose_id}.png").is_file()
    }

    old_poses: dict[str, pathlib.Path] = {}
    for pose_id in poses:
        source = pathlib.Path(settings.keyframe_storage_root_dir) / (
            f"{recorded[pose_id]['storage_key']}"
        )
        target = args.out / "poses-old" / f"{pose_id}.png"
        shutil.copyfile(source, target)
        old_poses[pose_id] = target

    rendered: dict[str, dict[str, object]] = {}
    if not args.dry_run:
        ram = free_ram_gb()
        if 0 <= ram < MIN_FREE_RAM_GB:
            raise SystemExit(
                f"Only {ram:.2f} GB RAM free; the render gate requires "
                f"{MIN_FREE_RAM_GB:.1f} GB. Close something and retry."
            )
        generator = get_keyframe_generation_provider(
            settings,
            capability=GenerationCapability.CHARACTER_POSE_PACK,
            storage=storage,
        )
        prompt_service = CharacterIdentityPromptService()
        lock = manifest.get("style_lock_snapshot") or {}
        assert approval.face_anchor is not None

        async def run() -> dict[str, dict[str, object]]:
            records: dict[str, dict[str, object]] = {}
            for pose_id in poses:
                pose = recorded[pose_id]
                labels = [
                    POSE_MATCH_VIEW[pose_id],
                    "FACE",
                ]
                references = tuple(
                    (
                        labels[index],
                        key,
                        digest,
                        0.75 if index == 0 else 0.50,
                    )
                    for index, (key, digest) in enumerate(
                        zip(pose["reference_storage_keys"], pose["reference_hashes"])
                    )
                )
                request = prompt_service.build_pose_request(
                    brief,
                    style_key=manifest["style_reference_storage_key"],
                    style_hash=manifest["style_reference_hash"],
                    pose_id=pose_id,
                    expected_view=POSE_MATCH_VIEW[pose_id],
                    seed=pose["seed"],
                    face_anchor_key=approval.face_anchor.storage_key,
                    face_anchor_hash=approval.face_anchor.content_hash,
                    fullbody_anchor_key=approval.fullbody_anchor.storage_key,
                    fullbody_anchor_hash=approval.fullbody_anchor.content_hash,
                    pose_template_key=pose["pose_template_storage_key"],
                    style_lock_snapshot=lock,
                    references=references,
                    width=settings.character_pose_pack_width,
                    height=settings.character_pose_pack_height,
                )
                generated = await generator.generate_keyframe(request)
                image_bytes, width, height = (
                    CharacterViewPackAssetService.normalized_png(
                        generated.image_bytes
                    )
                )
                expected = (
                    settings.character_pose_pack_width,
                    settings.character_pose_pack_height,
                )
                if (width, height) != expected:
                    raise SystemExit(
                        f"{pose_id}: rendered {width}x{height}, expected "
                        f"{expected[0]}x{expected[1]}"
                    )
                target = args.out / "poses-new" / f"{pose_id}.png"
                target.write_bytes(image_bytes)
                records[pose_id] = {
                    "pose_id": pose_id,
                    "seed": pose["seed"],
                    "references": [item[0] for item in references],
                    "reference_storage_keys": list(pose["reference_storage_keys"]),
                    "pose_template_storage_key": pose["pose_template_storage_key"],
                    "pose_template_hash": pose["pose_template_hash"],
                    "image": str(target),
                    "width": width,
                    "height": height,
                    "sha256": sha256(image_bytes),
                    "generation": dict(generated.metadata),
                }
            return records

        rendered = asyncio.run(run())

    old_silhouettes = {pose: silhouette_of(old_poses[pose]) for pose in poses}
    new_silhouettes = {
        pose: silhouette_of(args.out / "poses-new" / f"{pose}.png")
        for pose in poses
        if (args.out / "poses-new" / f"{pose}.png").is_file()
    }
    old_matrix = matrix(old_silhouettes, poses)
    new_matrix = matrix(new_silhouettes, poses) if len(new_silhouettes) == len(poses) else {}

    comparisons = {}
    for pose_id in poses:
        new_path = args.out / "poses-new" / f"{pose_id}.png"
        if not new_path.is_file():
            continue
        comparisons[pose_id] = {
            "iou_vs_previous_render": silhouette_iou(
                new_silhouettes[pose_id], old_silhouettes[pose_id]
            ),
            "palette_new": palette_of(new_path),
            "palette_old": palette_of(old_poses[pose_id]),
            "framing_new": framing_of(new_path),
            "framing_old": framing_of(old_poses[pose_id]),
        }
        comparisons[pose_id]["palette_distance"] = palette_distance(
            comparisons[pose_id]["palette_new"], comparisons[pose_id]["palette_old"]
        )

    payload = {
        "schema_version": 1,
        "character_id": manifest["character_id"],
        "character_version": manifest["character_version"],
        "pack_manifest": str(args.pack_dir / "manifest.json"),
        "poses": list(poses),
        "same_wing_pairs": [list(pair) for pair in SAME_WING],
        "guides": guide_records,
        "guide_iou_new": matrix(current_guides, tuple(current_guides)),
        "guide_iou_old": matrix(previous_guides, tuple(previous_guides)),
        "pose_iou_old": old_matrix,
        "pose_iou_new": new_matrix,
        "render_comparisons": comparisons,
        "renders": rendered,
    }
    (args.out / "divergence.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    changed = sorted(
        pose
        for pose in poses
        if guide_records.get(pose, {}).get("sha256")
        != guide_records.get(pose, {}).get("recorded_in_pack")
    )
    print(f"guide files that differ from what the pack recorded: {changed}")
    if len(current_guides) == len(poses):
        report_matrix("GUIDES (new)", matrix(current_guides, poses), poses)
    if len(previous_guides) == len(poses):
        report_matrix(
            f"GUIDES ({args.old_guide_rev})", matrix(previous_guides, poses), poses
        )
    report_matrix(
        f"POSES as packaged ({manifest['character_id']} v{manifest['character_version']})",
        old_matrix,
        poses,
    )
    if new_matrix:
        report_matrix("POSES redrawn on the corrected guides", new_matrix, poses)
    for pose_id, values in comparisons.items():
        print(
            f"\n{pose_id}: IoU vs previous render {values['iou_vs_previous_render']:.3f}"
            f" | palette delta {values['palette_distance']:.1f}"
            f" | width {values['framing_old']['left']:.3f}-"
            f"{values['framing_old']['right']:.3f} -> "
            f"{values['framing_new']['left']:.3f}-"
            f"{values['framing_new']['right']:.3f}"
        )
    print(f"\nwrote {args.out / 'divergence.json'}")


if __name__ == "__main__":
    main()
