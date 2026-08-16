from __future__ import annotations

import json
import hashlib
from pathlib import Path

from core.domain.exceptions import BackgroundMusicError
from core.domain.ports.background_music_port import BackgroundMusicPort
from core.domain.value_objects.background_track import BackgroundTrack


class LocalLicensedMusicProvider(BackgroundMusicPort):
    def __init__(self, library_dir: str) -> None:
        self._library_dir = Path(library_dir)

    async def select(
        self,
        theme: str,
        track_name: str | None = None,
    ) -> BackgroundTrack:
        manifest_path = self._library_dir / "license_manifest.json"
        if not manifest_path.is_file():
            raise BackgroundMusicError(
                f"Licensed music manifest not found: {manifest_path}."
            )
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BackgroundMusicError(f"Invalid music manifest: {exc}") from exc
        tracks = data.get("tracks") if isinstance(data, dict) else None
        if not isinstance(tracks, list) or not tracks:
            raise BackgroundMusicError("Music manifest contains no licensed tracks.")

        if track_name:
            normalized_override = track_name.casefold()
            tracks = [
                item
                for item in tracks
                if normalized_override
                in {
                    str(item.get("title") or "").casefold(),
                    str(item.get("file") or "").casefold(),
                    Path(str(item.get("file") or "")).stem.casefold(),
                }
            ]
            if not tracks:
                raise BackgroundMusicError(
                    f"Requested music track not found in manifest: {track_name!r}."
                )

        theme_tokens = set(theme.casefold().split())
        ranked = sorted(
            tracks,
            key=lambda item: len(
                theme_tokens
                & {str(value).casefold() for value in (item.get("themes") or [])}
            ),
            reverse=True,
        )
        selected = ranked[0]
        file_path = self._library_dir / str(selected.get("file") or "")
        attribution = str(selected.get("attribution") or "").strip()
        license_name = str(selected.get("license") or "").strip()
        if not file_path.is_file() or not attribution or not license_name:
            raise BackgroundMusicError(
                "Selected music track is missing its file, attribution, or license."
            )
        declared_hash = str(selected.get("sha256") or "").strip().casefold()
        if declared_hash:
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if actual_hash != declared_hash:
                raise BackgroundMusicError(
                    f"Licensed music checksum mismatch for '{file_path.name}'."
                )
        commercial_use = bool(selected.get("commercial_use", True))
        youtube_allowed = bool(selected.get("youtube_allowed", True))
        if not commercial_use or not youtube_allowed:
            raise BackgroundMusicError(
                "Selected music track is not cleared for commercial YouTube publishing."
            )
        schema_version = int(data.get("schema_version", 1))
        source_url = str(selected.get("source_url") or "").strip()
        evidence_reference = str(selected.get("evidence_reference") or "").strip()
        if schema_version >= 2 and (not declared_hash or not source_url or not evidence_reference):
            raise BackgroundMusicError(
                "Schema v2 music entries require sha256, source_url, and evidence_reference."
            )
        return BackgroundTrack(
            file_path=str(file_path.resolve()),
            title=str(selected.get("title") or file_path.stem),
            attribution=attribution,
            license=license_name,
            themes=[str(value) for value in (selected.get("themes") or [])],
            source_url=source_url,
            sha256=declared_hash,
            evidence_reference=evidence_reference,
            commercial_use=commercial_use,
            youtube_allowed=youtube_allowed,
            attribution_required=bool(selected.get("attribution_required", True)),
        )
