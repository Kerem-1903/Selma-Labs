"""Load and integrity-check one multi-character anime series project."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from core.application.services.model_lock_service import load_model_lock
from core.domain.entities.character_bible import CharacterBible
from core.domain.value_objects.series_project import (
    CastMember,
    CharacterRegistry,
    SeriesProject,
)


class SeriesProjectService:
    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()

    def load(self, project_path: str | Path) -> tuple[SeriesProject, CharacterRegistry]:
        source = self._inside_workspace(project_path)
        raw_project = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw_project, dict):
            raise TypeError("Series project must contain an object.")
        project = SeriesProject.from_dict(raw_project)
        self._validate_style_reference(project)

        registry_path = self._inside_workspace(project.character_registry)
        raw_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(raw_registry, dict):
            raise TypeError("Character registry must contain an object.")
        registry = CharacterRegistry.from_dict(raw_registry)
        if registry.series_id != project.series_id:
            raise ValueError("Character registry belongs to another series.")
        self._validate_members(registry)

        model_lock_path = self._inside_workspace(project.model_lock)
        load_model_lock(model_lock_path).entry("checkpoint")
        return project, registry

    def register_character(
        self,
        *,
        project_path: str | Path,
        bible_path: str | Path,
        role: str,
        version: int = 1,
        status: str = "DRAFT",
    ) -> CharacterRegistry:
        project, registry = self.load(project_path)
        bible_source = self._inside_workspace(bible_path)
        raw = json.loads(bible_source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("Character Bible must contain an object.")
        bible_payload = raw.get("character_bible", raw)
        if not isinstance(bible_payload, dict):
            raise TypeError("character_bible must contain an object.")
        bible = CharacterBible.from_dict(bible_payload)
        member = CastMember(
            character_id=bible.character_id,
            version=version,
            role=role,
            bible_path=bible_source.relative_to(self._workspace_root).as_posix(),
            status=status,
        )
        updated = registry.register(member)
        registry_path = self._inside_workspace(project.character_registry)
        self._write_json_atomic(registry_path, updated.to_dict())
        self._validate_members(updated)
        return updated

    def _validate_style_reference(self, project: SeriesProject) -> None:
        style = project.style_bible
        asset = self._inside_workspace(style.reference_asset)
        data = asset.read_bytes()
        if hashlib.sha256(data).hexdigest() != style.reference_sha256:
            raise ValueError("Approved series style reference hash mismatch.")
        try:
            with Image.open(asset) as image:
                dimensions = image.size
                image.verify()
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("Approved series style reference is not a valid image.") from error
        if dimensions != (style.width, style.height):
            raise ValueError("Approved series style reference dimensions mismatch.")

    def _validate_members(self, registry: CharacterRegistry) -> None:
        for member in registry.members:
            bible_path = self._inside_workspace(member.bible_path)
            raw = json.loads(bible_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise TypeError("Character Bible must contain an object.")
            bible_payload = raw.get("character_bible", raw)
            if not isinstance(bible_payload, dict):
                raise TypeError("character_bible must contain an object.")
            bible = CharacterBible.from_dict(bible_payload)
            if bible.character_id != member.character_id:
                raise ValueError(
                    f"Registry member {member.character_id} points to another character."
                )

    def _inside_workspace(self, path: str | Path) -> Path:
        candidate = Path(path)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (self._workspace_root / candidate).resolve()
        )
        resolved.relative_to(self._workspace_root)
        return resolved

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
