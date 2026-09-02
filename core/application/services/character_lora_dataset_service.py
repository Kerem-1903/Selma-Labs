from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import ClassVar

from PIL import Image, ImageOps

from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.character_lora_dataset import (
    CharacterLoraDatasetReport,
    CharacterLoraDatasetSample,
)


class CharacterLoraDatasetService:
    """Build a deterministic, reviewable LoRA dataset without training a model."""

    _IMAGE_SUFFIXES: ClassVar[frozenset[str]] = frozenset(
        {".jpg", ".jpeg", ".png", ".webp"}
    )
    _VIEW_BY_PREFIX: ClassVar[dict[str, str]] = {
        "action-katana-follow-through": "ACTION_KATANA_FOLLOW_THROUGH",
        "action-katana-overhead": "ACTION_KATANA_OVERHEAD",
        "action-katana-ready": "ACTION_KATANA_READY",
        "action-landing": "ACTION_LANDING",
        "action-crouched-guard": "ACTION_CROUCHED_GUARD",
        "action-running": "ACTION_RUNNING",
        "action-signature": "ACTION_SIGNATURE",
        "action-walking": "ACTION_WALKING",
        "action-wind": "ACTION_WIND",
        "back": "BACK",
        "face-closeup": "FACE_CLOSEUP",
        "front": "FRONT",
        "full-body": "FULL_BODY",
        "profile-left": "PROFILE_LEFT",
        "profile-right": "PROFILE_RIGHT",
        "three-quarter-right": "THREE_QUARTER_RIGHT",
        "three-quarter": "THREE_QUARTER_LEFT",
        "upper-body": "UPPER_BODY",
    }
    _VIEW_CAPTIONS: ClassVar[dict[str, str]] = {
        "ACTION_KATANA_FOLLOW_THROUGH": "full body, horizontal katana follow-through, two-handed grip, dynamic balanced pose",
        "ACTION_KATANA_OVERHEAD": "full body, overhead katana preparation, two-handed grip, planted stance",
        "ACTION_KATANA_READY": "full body, two-handed katana ready stance, blade angled upward",
        "ACTION_LANDING": "full body, controlled three-point landing, low dynamic pose",
        "ACTION_CROUCHED_GUARD": "full body, low crouched defensive guard, balanced stance",
        "ACTION_RUNNING": "full body, dynamic sprint, clear running silhouette",
        "ACTION_SIGNATURE": "full body, signature action, canonical props only",
        "ACTION_WALKING": "full body, natural mid-stride walk",
        "ACTION_WIND": "full body, standing in strong wind, hair swept to one side",
        "BACK": "full body, back view, complete outfit and hair silhouette",
        "FACE_CLOSEUP": "face close-up, neutral expression, facial identity reference",
        "FRONT": "front view, upper body, neutral standing pose",
        "FULL_BODY": "full body, neutral standing pose, complete outfit",
        "PROFILE_LEFT": "left profile view, facial silhouette",
        "PROFILE_RIGHT": "right profile view, facial silhouette",
        "THREE_QUARTER_LEFT": "three-quarter view, neutral pose",
        "THREE_QUARTER_RIGHT": "right three-quarter view, neutral pose",
        "UPPER_BODY": "upper body, neutral pose, complete jacket construction",
    }

    def __init__(
        self,
        *,
        minimum_dimension: int = 768,
        output_size: int = 1024,
        required_training_images: int = 20,
        required_holdout_images: int = 3,
    ) -> None:
        if minimum_dimension <= 0 or output_size <= 0:
            raise ValueError("Dataset image dimensions must be greater than zero.")
        if required_training_images <= 0 or required_holdout_images <= 0:
            raise ValueError("Dataset readiness counts must be greater than zero.")
        self._minimum_dimension = minimum_dimension
        self._output_size = output_size
        self._required_training_images = required_training_images
        self._required_holdout_images = required_holdout_images

    def build(
        self,
        *,
        source_dir: str | Path,
        output_dir: str | Path,
        character_id: str,
        trigger_token: str,
        rights_status: str = "original_character",
        character_bible: CharacterBible | None = None,
    ) -> CharacterLoraDatasetReport:
        source = Path(source_dir)
        output = Path(output_dir)
        if not source.is_dir():
            raise FileNotFoundError(
                f"Character reference directory not found: {source}"
            )
        if not character_id.strip() or not trigger_token.strip():
            raise ValueError("character_id and trigger_token must not be empty.")
        if character_bible and character_bible.character_id != character_id.strip():
            raise ValueError("Character Bible does not match the dataset character ID.")
        if rights_status != "original_character":
            raise ValueError("Only original-character assets can enter this dataset.")

        output.mkdir(parents=True, exist_ok=True)
        samples: list[CharacterLoraDatasetSample] = []
        rejected: list[dict[str, str]] = []
        duplicates: list[str] = []
        seen_hashes: set[str] = set()
        candidates = sorted(
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.casefold() in self._IMAGE_SUFFIXES
        )
        for path in candidates:
            if self._is_training_excluded(path):
                continue
            view = self._view_for(path)
            if view is None:
                rejected.append({"file": path.name, "reason": "unknown_view"})
                continue
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen_hashes:
                duplicates.append(path.name)
                continue
            seen_hashes.add(digest)
            try:
                with Image.open(path) as image:
                    image.load()
                    width, height = image.size
                    if min(width, height) < self._minimum_dimension:
                        rejected.append(
                            {"file": path.name, "reason": "resolution_too_small"}
                        )
                        continue
                    normalized = ImageOps.pad(
                        image.convert("RGB"),
                        (self._output_size, self._output_size),
                        method=Image.Resampling.LANCZOS,
                        color=(245, 245, 245),
                        centering=(0.5, 0.5),
                    )
            except (OSError, ValueError):
                rejected.append({"file": path.name, "reason": "unreadable_image"})
                continue

            split = "holdout" if view == "PROFILE_RIGHT" else "train"
            safe_id = re.sub(r"[^a-z0-9_-]+", "-", character_id.casefold()).strip("-")
            if not safe_id:
                raise ValueError("character_id must contain a filename-safe character.")
            sample_id = f"{safe_id}-{len(samples) + 1:04d}"
            relative_image = Path(split) / f"{sample_id}.png"
            relative_caption = Path(split) / f"{sample_id}.txt"
            image_path = output / relative_image
            caption_path = output / relative_caption
            image_path.parent.mkdir(parents=True, exist_ok=True)
            normalized.save(image_path, format="PNG", optimize=True)
            caption = self._caption(trigger_token, view, character_bible)
            caption_path.write_text(caption + "\n", encoding="utf-8")
            samples.append(
                CharacterLoraDatasetSample(
                    sample_id=sample_id,
                    source_name=path.name,
                    view=view,
                    split=split,
                    image_path=relative_image.as_posix(),
                    caption_path=relative_caption.as_posix(),
                    caption=caption,
                    content_hash=digest,
                    width=self._output_size,
                    height=self._output_size,
                )
            )

        report = CharacterLoraDatasetReport(
            schema_version=1,
            character_id=character_id.strip(),
            trigger_token=trigger_token.strip(),
            samples=tuple(samples),
            rejected_files=tuple(rejected),
            duplicate_files=tuple(duplicates),
            required_training_images=self._required_training_images,
            required_holdout_images=self._required_holdout_images,
        )
        manifest_path = output / "manifest.json"
        temporary_path = manifest_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(
                {
                    **report.to_dict(),
                    "rights_status": rights_status,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary_path.replace(manifest_path)
        return report

    @classmethod
    def _view_for(cls, path: Path) -> str | None:
        normalized = path.stem.casefold()
        return next(
            (
                view
                for prefix, view in cls._VIEW_BY_PREFIX.items()
                if normalized.startswith(prefix)
            ),
            None,
        )

    @staticmethod
    def _is_training_excluded(path: Path) -> bool:
        normalized = path.as_posix().casefold()
        return "master-sheet" in normalized or "/poses/" in normalized

    @classmethod
    def _caption(
        cls,
        trigger_token: str,
        view: str,
        character_bible: CharacterBible | None,
    ) -> str:
        identity = (
            character_bible.prompt_fragments()
            if character_bible
            else ("original anime character",)
        )
        return ", ".join(
            dict.fromkeys(
                (
                    trigger_token.strip(),
                    *identity,
                    cls._VIEW_CAPTIONS[view],
                )
            )
        )
