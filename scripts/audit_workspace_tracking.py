"""Classify dirty-worktree files and flag source code that is not protected by Git."""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import PurePosixPath

GENERATED_PREFIXES = (
    "output/", ".selma_runs", ".codex_video_review/", "motion/out/",
    "motion/node_modules/", "__pycache__/", ".pytest_cache/",
)
SOURCE_PREFIXES = (
    "core/", "infrastructure/", "config/", "scripts/", "tests/", "motion/src/",
)
SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx"}
LFS_MEDIA_EXTENSIONS = {".mp4", ".mov", ".webm", ".mp3", ".wav"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".svg"}
CONFIG_NAMES = {
    ".gitignore", ".gitattributes", ".env.example", "requirements.txt",
    "requirements-ci.txt",
    "motion/package.json", "motion/package-lock.json", "motion/tsconfig.json",
}
PROTECTED_CATEGORIES = {
    "source", "configuration", "documentation", "asset_manifest",
}


def _status_entries() -> list[tuple[str, str]]:
    process = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        check=True,
        stdout=subprocess.PIPE,
    )
    chunks = process.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    entries: list[tuple[str, str]] = []
    for chunk in chunks:
        if not chunk:
            continue
        status = chunk[:2]
        path = chunk[3:].replace("\\", "/")
        entries.append((status, path))
    return entries


def _category(path: str) -> str:
    suffix = PurePosixPath(path).suffix.casefold()
    if path.startswith(GENERATED_PREFIXES):
        return "generated_output"
    if path.startswith("reference/"):
        return "local_reference"
    if path in CONFIG_NAMES or path.startswith(".github/"):
        return "configuration"
    if path.startswith(SOURCE_PREFIXES) and suffix in SOURCE_EXTENSIONS:
        return "source"
    if path.startswith("motion/") and suffix in {".json", ".md"}:
        return "configuration"
    if path.startswith("docs/") or suffix == ".md":
        return "documentation"
    if path.startswith(("assets/", "motion/public/")) and suffix in LFS_MEDIA_EXTENSIONS:
        return "production_media_lfs"
    if path.startswith(("assets/", "motion/public/")) and suffix in IMAGE_EXTENSIONS:
        return "production_image_asset"
    if path.startswith("assets/") and suffix in {".json", ".md"}:
        return "asset_manifest"
    return "unclassified"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-untracked-source", action="store_true")
    parser.add_argument("--show", type=int, default=8)
    args = parser.parse_args()

    entries = _status_entries()
    untracked_counts: Counter[str] = Counter()
    modified_counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    untracked_protected: list[str] = []
    modified = 0
    untracked = 0
    for status, path in entries:
        category = _category(path)
        target_counts = untracked_counts if status == "??" else modified_counts
        target_counts[category] += 1
        if len(examples[category]) < max(0, args.show):
            examples[category].append(path)
        if status == "??":
            untracked += 1
            if category in PROTECTED_CATEGORIES:
                untracked_protected.append(path)
        else:
            modified += 1

    result = {
        "modified_tracked_files": modified,
        "untracked_files": untracked,
        "untracked_protected_files": len(untracked_protected),
        "untracked_categories": dict(sorted(untracked_counts.items())),
        "modified_categories": dict(sorted(modified_counts.items())),
        "examples": dict(sorted(examples.items())),
        "policy": {
            "source_configuration_documentation": "track in Git",
            "production_media": "track only with Git LFS and license evidence",
            "production_images": "track after rights audit; use LFS above 5 MB",
            "local_reference": "keep local; do not commit without rights audit",
            "generated_output": "ignore and regenerate",
        },
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.fail_on_untracked_source and untracked_protected:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
