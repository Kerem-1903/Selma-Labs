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
    CharacterLoraSampleReview,
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
        "upper-body-rear-three-quarter": "UPPER_BODY_REAR_THREE_QUARTER",
        "upper-body-three-quarter-right": "UPPER_BODY_THREE_QUARTER_RIGHT",
        "upper-body-three-quarter-left": "UPPER_BODY_THREE_QUARTER_LEFT",
        "full-body-three-quarter-left": "FULL_BODY_THREE_QUARTER_LEFT",
        "full-body-profile-left": "FULL_BODY_PROFILE_LEFT",
        "profile-right-face-closeup": "PROFILE_RIGHT_FACE_CLOSEUP",
        "profile-right-full-body": "PROFILE_RIGHT_FULL_BODY",
        "profile-right-upper-body": "PROFILE_RIGHT_UPPER_BODY",
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
        "UPPER_BODY_REAR_THREE_QUARTER": "upper body, rear three-quarter view, complete jacket back construction",
        "UPPER_BODY_THREE_QUARTER_LEFT": "upper body, left three-quarter view, complete jacket construction",
        "UPPER_BODY_THREE_QUARTER_RIGHT": "upper body, right three-quarter view, complete jacket construction",
        "FULL_BODY_THREE_QUARTER_LEFT": "full body, left three-quarter view, neutral standing pose, complete outfit",
        "FULL_BODY_PROFILE_LEFT": "full body, strict left profile view, neutral standing pose, complete outfit",
        "PROFILE_RIGHT_FACE_CLOSEUP": "face close-up, strict right profile view, facial silhouette",
        "PROFILE_RIGHT_FULL_BODY": "full body, strict right profile view, neutral standing pose, complete outfit",
        "PROFILE_RIGHT_UPPER_BODY": "upper body, strict right profile view, complete jacket construction",
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
        review_manifest: str | Path | None = None,
        canonical_anchor: str | Path | None = None,
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

        reviews, approved_by, reviewed_anchor_hash = self._load_reviews(
            review_manifest, character_id=character_id.strip()
        )
        anchor_hash = self._anchor_hash(canonical_anchor)
        if reviewed_anchor_hash and reviewed_anchor_hash != anchor_hash:
            raise ValueError(
                "Canonical anchor does not match the reviewed anchor hash."
            )
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

            split = "holdout" if view.startswith("PROFILE_RIGHT") else "train"
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
                    review=self._review_for(reviews, path.name, digest),
                )
            )

        report = CharacterLoraDatasetReport(
            schema_version=2,
            character_id=character_id.strip(),
            trigger_token=trigger_token.strip(),
            samples=tuple(samples),
            rejected_files=tuple(rejected),
            duplicate_files=tuple(duplicates),
            required_training_images=self._required_training_images,
            required_holdout_images=self._required_holdout_images,
            anchor_content_hash=anchor_hash,
            approved_by=approved_by,
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

    @staticmethod
    def _load_reviews(
        review_manifest: str | Path | None, *, character_id: str
    ) -> tuple[dict[str, object], str, str]:
        if review_manifest is None:
            return {}, "", ""
        payload = json.loads(Path(review_manifest).read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("Unsupported character dataset review schema version.")
        if str(payload.get("character_id", "")).strip() != character_id:
            raise ValueError("Dataset review character does not match the dataset.")
        reviews = payload.get("reviews")
        if not isinstance(reviews, dict):
            raise TypeError("Dataset review manifest requires a reviews object.")
        return (
            reviews,
            str(payload.get("approved_by", "")).strip(),
            str(payload.get("canonical_anchor_sha256", "")).strip(),
        )

    @staticmethod
    def _review_for(
        reviews: dict[str, object], source_name: str, content_hash: str
    ) -> CharacterLoraSampleReview | None:
        raw = reviews.get(source_name)
        if not isinstance(raw, dict):
            return None
        return CharacterLoraSampleReview(
            identity_score=float(raw.get("identity_score", 0.0)),
            anatomy_score=float(raw.get("anatomy_score", 0.0)),
            caption_matches=bool(raw.get("caption_matches", False)),
            human_approved=bool(raw.get("human_approved", False)),
            reviewer=str(raw.get("reviewer", "")).strip(),
            reviewed_content_hash=str(raw.get("content_hash", "")).strip(),
            content_hash_matches=(
                str(raw.get("content_hash", "")).strip() == content_hash
            ),
            notes=str(raw.get("notes", "")),
        )

    @staticmethod
    def _anchor_hash(canonical_anchor: str | Path | None) -> str:
        if canonical_anchor is None:
            return ""
        path = Path(canonical_anchor)
        if not path.is_file():
            raise FileNotFoundError(f"Canonical identity anchor not found: {path}")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def _view_for(cls, path: Path) -> str | None:
        normalized = path.stem.casefold()
        return next(
            (
                view
                for prefix, view in sorted(
                    cls._VIEW_BY_PREFIX.items(),
                    key=lambda item: len(item[0]),
                    reverse=True,
                )
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
