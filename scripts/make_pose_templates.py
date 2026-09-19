"""Render the canonical OpenPose view templates and refresh their catalog.

The previous generator lived in a git-ignored directory, so the production
assets could not be reproduced from the repository at all. This one is
versioned, and it draws every view from the single yaw-projected rig in
`core.domain.services.pose_template_rig` rather than from per-view special
cases -- the special cases are what collapsed the three-quarter templates into
side views.

    python -m scripts.make_pose_templates            # write + refresh catalog
    python -m scripts.make_pose_templates --check     # verify the catalog only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from PIL import Image, ImageDraw

from core.domain.services.pose_template_rig import LIMBS, project_frame

W, H = 768, 1152

#: Official OpenPose body-18 limb colours, keyed by the limb's first joint.
COLOURS: dict[str, tuple[int, int, int]] = {
    "head": (255, 0, 0),
    "neck": (255, 85, 0),
    "r_shoulder": (255, 170, 0),
    "r_elbow": (255, 255, 0),
    "r_wrist": (170, 255, 0),
    "l_shoulder": (85, 255, 0),
    "l_elbow": (0, 255, 0),
    "l_wrist": (0, 255, 85),
    "r_hip": (0, 255, 170),
    "r_knee": (0, 255, 255),
    "r_ankle": (0, 170, 255),
    "l_hip": (0, 85, 255),
    "l_knee": (0, 0, 255),
    "l_ankle": (85, 0, 255),
    "l_eye": (170, 0, 255),
    "l_ear": (255, 0, 255),
    "r_eye": (255, 0, 170),
    "r_ear": (255, 0, 85),
}

LINE_WIDTH = 14
JOINT_RADIUS = 7
HEAD_RADIUS = 16

#: File each view is written to. `BACK` keeps its versioned name because the
#: staged storage key `characters/_pose_templates/pose_back_v5.png` is recorded
#: inside every existing pose pack's evidence.
FILES: dict[str, str] = {
    "FRONT": "pose_front.png",
    "PROFILE_LEFT": "pose_profile_left.png",
    "PROFILE_RIGHT": "pose_profile_right.png",
    "BACK": "pose_back_v5.png",
}

#: The legacy alias some design code still resolves. Kept byte-identical to the
#: catalogued back template so both keys describe one drawing.
BACK_ALIAS = "pose_back.png"

SOURCE_DIR = pathlib.Path(__file__).resolve().parents[1] / "assets" / "pose_templates"
CATALOG = SOURCE_DIR / "catalog.json"


def render(view: str) -> Image.Image:
    """Draw the skeleton for one view on black, at production size."""
    joints = {
        name: (x * W, y * H) for name, (x, y) in project_frame(view).items()
    }
    image = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    for first, second in LIMBS:
        draw.line(
            [joints[first], joints[second]],
            fill=COLOURS.get(first, COLOURS["neck"]),
            width=LINE_WIDTH,
        )
    hx, hy = joints["head"]
    draw.ellipse(
        [hx - HEAD_RADIUS, hy - HEAD_RADIUS, hx + HEAD_RADIUS, hy + HEAD_RADIUS],
        fill=COLOURS["head"],
    )
    for name, colour in COLOURS.items():
        if name not in joints:
            continue
        x, y = joints[name]
        draw.ellipse(
            [x - JOINT_RADIUS, y - JOINT_RADIUS, x + JOINT_RADIUS, y + JOINT_RADIUS],
            fill=colour,
        )
    return image


def png_bytes(image: Image.Image) -> bytes:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_catalog(payload: dict[str, object]) -> dict[str, object]:
    """Return the catalog with every entry re-hashed from the rendered bytes."""
    entries = []
    for view, filename in FILES.items():
        data = png_bytes(render(view))
        entries.append(
            {
                "view": view,
                "filename": filename,
                "sha256": hashlib.sha256(data).hexdigest(),
                "width": W,
                "height": H,
            }
        )
    payload["templates"] = entries
    payload["aliases"] = [
        {
            "filename": BACK_ALIAS,
            "canonical": FILES["BACK"],
            "sha256": hashlib.sha256(png_bytes(render("BACK"))).hexdigest(),
            "note": (
                "Byte-identical to the BACK template. Kept because "
                "character_design_service still resolves this key."
            ),
        }
    ]
    payload["generator"] = (
        "scripts/make_pose_templates.py -- one yaw-projected rig, no per-view "
        "special cases"
    )
    return payload


def write(source_dir: pathlib.Path) -> list[pathlib.Path]:
    written: list[pathlib.Path] = []
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    for view, filename in FILES.items():
        target = source_dir / filename
        target.write_bytes(png_bytes(render(view)))
        written.append(target)
    alias = source_dir / BACK_ALIAS
    alias.write_bytes(png_bytes(render("BACK")))
    written.append(alias)
    CATALOG.write_text(
        json.dumps(build_catalog(catalog), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return written


def check(source_dir: pathlib.Path) -> list[str]:
    """Return the names of template files that disagree with the catalog."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    listed = [*catalog.get("templates", []), *catalog.get("aliases", [])]
    entries = {
        str(item.get("filename")): str(item.get("sha256"))
        for item in listed
        if isinstance(item, dict)
    }
    stale: list[str] = []
    for filename, expected in entries.items():
        path = source_dir / filename
        if not path.is_file():
            stale.append(f"{filename}: missing")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            stale.append(f"{filename}: hash mismatch")
    for view, filename in FILES.items():
        expected = hashlib.sha256(png_bytes(render(view))).hexdigest()
        if entries.get(filename) != expected:
            stale.append(f"{filename}: catalog differs from a fresh render")
    return stale


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=pathlib.Path, default=SOURCE_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        stale = check(args.source_dir)
        for line in stale:
            print(f"STALE {line}")
        print("catalog consistent" if not stale else "catalog stale")
        raise SystemExit(1 if stale else 0)
    for path in write(args.source_dir):
        print(f"wrote {path}")
    print(f"updated {CATALOG}")


if __name__ == "__main__":
    main()
