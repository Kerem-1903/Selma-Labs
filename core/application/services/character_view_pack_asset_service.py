"""Storage, QC evidence, and provenance helpers for canonical view packs."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import cast

from PIL import Image, UnidentifiedImageError

from core.application.services.production_manifest_service import ProductionManifestService
from core.domain.exceptions import KeyframeGenerationError, StorageError
from core.domain.ports.storage_port import StoragePort
from core.domain.value_objects.character_design import (
    CharacterAnchorArtifact,
    CharacterReferenceDraft,
    CharacterViewQuarantineArtifact,
)
from core.domain.value_objects.character_view_qc import CharacterViewQcReport
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest


class CharacterViewPackAssetService:
    """Own byte locks, QC evidence artifacts, templates, and provenance records."""

    _POSE_TEMPLATE_KEYS = {
        "PROFILE_LEFT": "characters/_pose_templates/pose_profile_left.png",
        "PROFILE_RIGHT": "characters/_pose_templates/pose_profile_right.png",
        "BACK": "characters/_pose_templates/pose_back_v5.png",
    }
    _POSE_TEMPLATE_SOURCE_DIR = Path(__file__).resolve().parents[3] / "assets" / "pose_templates"
    _ANCHOR_WORKFLOW_VERSION = "dual-anchor-v2-deterministic"

    def __init__(
        self,
        storage: StoragePort,
        *,
        production_manifest: ProductionManifestService | None = None,
        pose_template_keys: dict[str, str] | None = None,
        pose_template_sources: dict[str, str] | None = None,
    ) -> None:
        self._storage = storage
        self._production_manifest = production_manifest
        self._pose_template_keys = dict(pose_template_keys or self._POSE_TEMPLATE_KEYS)
        self._pose_template_sources = dict(pose_template_sources or {})

    async def verify_anchor(self, anchor: CharacterAnchorArtifact) -> None:
        if not await self._storage.exists(anchor.storage_key):
            raise StorageError(f"Canonical anchor '{anchor.storage_key}' was not found.")
        data = await self._storage.load(anchor.storage_key)
        if hashlib.sha256(data).hexdigest() != anchor.content_hash:
            raise ValueError(f"Canonical {anchor.role} anchor changed after approval.")

    async def ensure_pose_templates(self) -> None:
        catalog_path = self._POSE_TEMPLATE_SOURCE_DIR / "catalog.json"
        if not catalog_path.is_file():
            raise StorageError(f"Pose template catalog is missing: {catalog_path}")
        raw_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        if not isinstance(raw_catalog, dict) or raw_catalog.get("schema_version") != 1:
            raise StorageError("Pose template catalog is malformed.")
        entries = raw_catalog.get("templates")
        if not isinstance(entries, list):
            raise StorageError("Pose template catalog has no template list.")
        by_view = {str(entry.get("view")): entry for entry in entries if isinstance(entry, dict)}
        for view, storage_key in self._pose_template_keys.items():
            entry = by_view.get(view)
            if entry is None:
                raise StorageError(f"Pose template catalog has no {view} entry.")
            source_filename = self._pose_template_sources.get(
                view, str(entry.get("filename", ""))
            )
            source = self._POSE_TEMPLATE_SOURCE_DIR / source_filename
            if not source.is_file():
                raise StorageError(f"Pose template source is missing: {source}")
            source_bytes = source.read_bytes()
            try:
                with Image.open(io.BytesIO(source_bytes)) as opened:
                    dimensions = opened.size
                    opened.verify()
            except (UnidentifiedImageError, OSError) as error:
                raise StorageError(f"Pose template is not a valid image: {source}") from error
            digest = hashlib.sha256(source_bytes).hexdigest()
            expected_digest = str(entry.get("sha256", ""))
            if digest != expected_digest:
                if self._pose_template_sources.get(view) is None:
                    raise StorageError(f"Pose template hash mismatch: {source.name}")
                expected_digest = digest
            if dimensions != (int(entry.get("width", 0)), int(entry.get("height", 0))):
                raise StorageError(f"Pose template dimensions mismatch: {source.name}")
            if await self._storage.exists(storage_key):
                stored = await self._storage.load(storage_key)
                if hashlib.sha256(stored).hexdigest() != digest:
                    raise StorageError(f"Installed pose template changed unexpectedly: {storage_key}")
                continue
            saved = await self._storage.save(storage_key, source_bytes, "image/png")
            if saved.key != storage_key:
                raise StorageError("Storage adapter returned a different pose template key.")

    async def quarantine_view(
        self,
        *,
        root: str,
        view: str,
        seed: int,
        attempt: int,
        image_bytes: bytes,
        content_hash: str,
        report: CharacterViewQcReport,
    ) -> CharacterViewQuarantineArtifact:
        reason = report.reasons[0] if report.reasons else "unknown"
        reason = "".join(character if character.isalnum() or character in "-_" else "-" for character in reason)[:80]
        stem = f"{view.casefold()}_seed{seed}_fail_{reason}_{content_hash[:12]}"
        image_key = f"{root}/quarantine/{stem}.png"
        report_key = f"{root}/quarantine/{stem}.json"
        await self.save_locked_asset(image_key, image_bytes, content_hash)
        payload = {"schema_version": 1, "attempt": attempt, "content_hash": content_hash, **report.to_dict()}
        report_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
        await self.save_locked_asset(
            report_key,
            report_bytes,
            hashlib.sha256(report_bytes).hexdigest(),
            content_type="application/json",
        )
        return CharacterViewQuarantineArtifact(
            view=view,
            seed=seed,
            attempt=attempt,
            image_storage_key=image_key,
            report_storage_key=report_key,
            content_hash=content_hash,
            reasons=report.reasons,
        )

    async def contact_sheet(self, drafts: list[CharacterReferenceDraft]) -> bytes:
        tile_width, tile_height, label_height = 320, 480, 32
        sheet = Image.new("RGB", (tile_width * 4, (tile_height + label_height) * 2), "white")
        for index, draft in enumerate(drafts):
            image_bytes = await self._storage.load(draft.storage_key)
            if hashlib.sha256(image_bytes).hexdigest() != draft.content_hash:
                raise ValueError(f"View '{draft.view}' changed before contact-sheet creation.")
            with Image.open(io.BytesIO(image_bytes)) as source:
                tile = source.convert("RGB")
                tile.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
            left = (index % 4) * tile_width + (tile_width - tile.width) // 2
            top = (index // 4) * (tile_height + label_height)
            sheet.paste(tile, (left, top))
            from PIL import ImageDraw
            ImageDraw.Draw(sheet).text(((index % 4) * tile_width + 8, top + tile_height + 8), draft.view.replace("_", " "), fill="black")
        output = io.BytesIO()
        sheet.save(output, format="PNG", optimize=True)
        return output.getvalue()

    def record_manifest_asset(
        self,
        *,
        root: str,
        asset_id: str,
        storage_key: str,
        content_hash: str,
        seed: int,
        reference_hashes: tuple[str, ...],
        report: CharacterViewQcReport,
        generation_metadata: dict[str, object],
        state: str,
    ) -> None:
        if self._production_manifest is None:
            return
        raw_model_hashes = generation_metadata.get("model_hashes", {})
        model_hashes = ({str(key): str(value) for key, value in raw_model_hashes.items()} if isinstance(raw_model_hashes, dict) else {})
        raw_peak = generation_metadata.get("peak_vram_mb")
        self._production_manifest.record_asset(
            relative_root=root,
            asset_id=asset_id,
            storage_key=storage_key,
            content_hash=content_hash,
            seed=seed,
            model_hashes=model_hashes,
            reference_hashes=reference_hashes,
            qc_metrics=report.to_dict(),
            render_duration_sec=float(
                cast(float | str, generation_metadata.get("render_duration_sec", 0.0))
            ),
            peak_vram_mb=float(cast(float | str, raw_peak)) if raw_peak is not None else None,
            state=state,
            prompt_hash=str(generation_metadata.get("prompt_hash", "")),
            workflow_hash=str(generation_metadata.get("workflow_hash", "")),
        )

    async def save_locked_asset(
        self,
        storage_key: str,
        data: bytes,
        content_hash: str,
        *,
        content_type: str = "image/png",
        allow_replace: bool = False,
    ) -> None:
        """Write one character asset, refusing to clobber different bytes.

        ``allow_replace`` exists for exactly one caller: a targeted re-render
        of an already-drawn view, which deliberately replaces a render inside a
        pack that is still `PENDING_HUMAN_REVIEW`. The render it replaces is
        archived as quarantine evidence first, so the replacement is recorded
        rather than silent. Every other path keeps the fail-closed default.
        """
        if await self._storage.exists(storage_key):
            existing_hash = hashlib.sha256(await self._storage.load(storage_key)).hexdigest()
            if existing_hash == content_hash:
                return
            if not allow_replace:
                raise ValueError(f"Canonical asset '{storage_key}' is already locked to other bytes.")
        stored = await self._storage.save(storage_key, data, content_type)
        if stored.key != storage_key:
            raise StorageError("Storage adapter returned a different character asset key.")

    @staticmethod
    def request_hash(request: KeyframeGenerationRequest) -> str:
        payload = json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def normalized_png(data: bytes) -> tuple[bytes, int, int]:
        try:
            with Image.open(io.BytesIO(data)) as source:
                image = source.convert("RGB")
                width, height = image.size
                output = io.BytesIO()
                image.save(output, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise KeyframeGenerationError("Character view provider returned an unreadable image.") from error
        if width <= 0 or height <= 0:
            raise KeyframeGenerationError("Character view provider returned invalid image dimensions.")
        return output.getvalue(), width, height
