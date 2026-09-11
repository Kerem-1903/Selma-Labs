"""Validate the runtime media references of the active Remotion composition."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class RemotionMediaInventory:
    """Inventory dynamic AnimeAnimatic props against the public directory."""

    @staticmethod
    def validate_props(props_path: str | Path, public_directory: str | Path) -> tuple[str, ...]:
        path = Path(props_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("Remotion props must contain a JSON object.")
        return RemotionMediaInventory.validate(payload, public_directory)

    @staticmethod
    def validate(
        props: Mapping[str, Any], public_directory: str | Path
    ) -> tuple[str, ...]:
        public = Path(public_directory).resolve()
        references: list[str] = []
        for clip in props.get("clips", ()):
            if not isinstance(clip, Mapping):
                raise TypeError("Remotion clips must be objects.")
            for field in ("imageSrc", "audioSrc"):
                reference = str(clip.get(field, "")).strip()
                if reference and not reference.startswith("placeholder://"):
                    references.append(reference)
        for cue in props.get("audioCues", ()):
            if not isinstance(cue, Mapping):
                raise TypeError("Remotion audio cues must be objects.")
            reference = str(cue.get("storage_key", "")).strip()
            if reference:
                references.append(reference)

        missing: list[str] = []
        for reference in dict.fromkeys(references):
            candidate = (public / Path(reference.replace("/", "\\"))).resolve()
            try:
                candidate.relative_to(public)
            except ValueError as error:
                raise ValueError(
                    f"Remotion media reference escapes public directory: {reference}"
                ) from error
            if not candidate.is_file():
                missing.append(reference)
        return tuple(missing)
