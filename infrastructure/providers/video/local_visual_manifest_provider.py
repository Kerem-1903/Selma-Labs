"""Fail-closed adapter for operator-approved local visual manifests."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from core.domain.entities.media_asset import MediaAsset
from core.domain.ports.visual_manifest_port import VisualManifestPort
from core.domain.value_objects.asset_diversity import AssetUsage
from core.domain.value_objects.visual_intent import VisualIntent


class LocalVisualManifestProvider(VisualManifestPort):
    """Load pre-reviewed clips without weakening the normal vision gate.

    This route is explicit and auditable: the manifest must be marked as
    operator-approved, every beat needs its own file, and license metadata is
    mandatory. It is intended for owned footage, generated visuals, or clips
    reviewed outside an automated vision provider.
    """

    _SUPPORTED_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}

    def __init__(self, manifest_path: str | Path) -> None:
        self._manifest_path = Path(manifest_path).resolve()

    def select(
        self,
        visual_intents: Sequence[VisualIntent],
    ) -> tuple[list[MediaAsset], list[AssetUsage]]:
        if not visual_intents:
            raise ValueError("A visual manifest cannot be selected without visual intents.")
        data = self._read_manifest()
        entries = data.get("assets")
        if not isinstance(entries, list) or len(entries) < len(visual_intents):
            found = len(entries) if isinstance(entries, list) else 0
            raise ValueError(
                "The approved visual manifest requires at least one unique asset "
                f"per visual intent; required={len(visual_intents)}, found={found}."
            )

        assets: list[MediaAsset] = []
        usages: list[AssetUsage] = []
        seen_ids: set[str] = set()
        seen_paths: set[Path] = set()
        for index, (intent, raw_entry) in enumerate(zip(visual_intents, entries)):
            if not isinstance(raw_entry, dict):
                raise ValueError(f"Visual manifest asset {index} must be an object.")
            entry: dict[str, Any] = raw_entry
            file_path = self._resolve_file(entry, index)
            asset_id = str(entry.get("id") or f"local:{file_path.stem}").strip()
            if not asset_id or asset_id in seen_ids or file_path in seen_paths:
                raise ValueError(
                    f"Visual manifest asset {index} must have a unique id and file."
                )
            attribution = str(entry.get("attribution") or "").strip()
            license_name = str(entry.get("license") or "").strip()
            if not attribution or not license_name:
                raise ValueError(
                    f"Visual manifest asset {index} is missing attribution or license."
                )
            motion_energy = float(entry.get("motion_energy", 0.55))
            if not 0.0 <= motion_energy <= 1.0:
                raise ValueError(
                    f"Visual manifest asset {index} motion_energy must be between 0 and 1."
                )

            content_fingerprint = self._content_fingerprint(file_path)
            provider = str(entry.get("provider") or "local-reviewed").strip()
            provider_asset_id = str(
                entry.get("provider_asset_id") or file_path.stem
            ).strip()
            asset = MediaAsset(
                id=asset_id,
                provider=provider,
                provider_asset_id=provider_asset_id,
                media_type="video",
                original_url=str(entry.get("source_url") or "").strip(),
                attribution=attribution,
                license=license_name,
                local_path=str(file_path),
                tags=[str(value) for value in entry.get("tags", [])],
                metadata={
                    "operator_approved": True,
                    "manifest_path": str(self._manifest_path),
                    "content_fingerprint": content_fingerprint,
                },
            )
            assets.append(asset)
            usages.append(
                AssetUsage(
                    asset_id=asset_id,
                    perceptual_hashes=(content_fingerprint,),
                    visual_job=intent.visual_job,
                    shot_type=intent.shot_type,
                    explanation_mode=intent.explanation_mode,
                    overlay_labels=intent.overlay_labels,
                    subject_pose=str(entry.get("subject_pose") or "reviewed"),
                    camera_angle=str(entry.get("camera_angle") or intent.shot_type),
                    background_signature=str(
                        entry.get("background_signature") or content_fingerprint
                    ),
                    motion_energy=motion_energy,
                    start_ms=intent.start_ms,
                    end_ms=intent.end_ms,
                )
            )
            seen_ids.add(asset_id)
            seen_paths.add(file_path)
        return assets, usages

    def _read_manifest(self) -> dict[str, Any]:
        if not self._manifest_path.is_file():
            raise ValueError(f"Visual manifest not found: {self._manifest_path}.")
        try:
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid visual manifest: {error}") from error
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Visual manifest schema_version must be 1.")
        if data.get("operator_approved") is not True:
            raise ValueError(
                "Visual manifest must set operator_approved=true after human review."
            )
        return data

    def _resolve_file(self, entry: dict[str, Any], index: int) -> Path:
        raw_file = str(entry.get("file") or "").strip()
        if not raw_file:
            raise ValueError(f"Visual manifest asset {index} has no file.")
        library_root = self._manifest_path.parent.resolve()
        file_path = (library_root / raw_file).resolve()
        try:
            file_path.relative_to(library_root)
        except ValueError as error:
            raise ValueError(
                f"Visual manifest asset {index} escapes the manifest directory."
            ) from error
        if file_path.suffix.casefold() not in self._SUPPORTED_SUFFIXES:
            raise ValueError(f"Visual manifest asset {index} has an unsupported format.")
        if not file_path.is_file() or file_path.stat().st_size <= 0:
            raise ValueError(f"Visual manifest asset {index} file is missing or empty.")
        return file_path

    @staticmethod
    def _content_fingerprint(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()[:24]
