"""Fail-closed readiness checks for anime visual and animation stages."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.application.services.model_lock_service import (
    load_model_lock,
    verify_model_lock,
)
from core.domain.value_objects.series_project import CharacterRegistry, SeriesProject
from core.domain.value_objects.system_health import (
    SystemHealthCheck,
    SystemHealthReport,
)

VISUAL = "visual"
ANIMATION = "animation"


class AnimeProductionReadinessService:
    """Validate inputs before local visual generation or rented-GPU animation."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        executable_lookup: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._lookup = executable_lookup

    def evaluate(
        self,
        stage: str,
        *,
        series_project: str | Path = "config/series/selma-anime-v1.json",
        episode_root: str | Path | None = None,
        requirements_path: str | Path | None = None,
        full_model_hash: bool = False,
    ) -> SystemHealthReport:
        if stage not in {VISUAL, ANIMATION}:
            raise ValueError("Anime readiness stage must be visual or animation.")
        default = (
            "config/production/anime-visual-requirements.json"
            if stage == VISUAL
            else "config/production/anime-animation-requirements.json"
        )
        requirements, requirement_check = self._load_json(
            requirements_path or default,
            name="requirements_manifest",
        )
        checks = [requirement_check]
        if requirements is not None:
            checks.extend(self._tool_checks(requirements, stage))
            if stage == VISUAL:
                checks.extend(
                    self._visual_checks(
                        series_project,
                        requirements,
                        full_model_hash=full_model_hash,
                    )
                )
            else:
                checks.extend(self._animation_checks(episode_root, requirements))
        ready = not any(check.required and check.status == "FAIL" for check in checks)
        return SystemHealthReport(
            profile=f"anime-{stage}",
            ready=ready,
            checks=tuple(checks),
        )

    def _visual_checks(
        self,
        project_path: str | Path,
        requirements: dict[str, Any],
        *,
        full_model_hash: bool,
    ) -> list[SystemHealthCheck]:
        checks: list[SystemHealthCheck] = []
        raw_project, project_check = self._load_json(
            project_path, name="series_project"
        )
        checks.append(project_check)
        if raw_project is None:
            return checks
        try:
            project = SeriesProject.from_dict(raw_project)
        except (TypeError, ValueError) as error:
            checks.append(
                self._fail("series_contract", f"Invalid series project: {error}")
            )
            return checks

        checks.append(
            self._result(
                "approved_style",
                project.style_bible.status == "APPROVED",
                f"Style status is {project.style_bible.status}.",
                "Approve and promote the series style before production generation.",
            )
        )
        reference = self._resolve(project.style_bible.reference_asset)
        reference_ok = (
            reference.is_file()
            and self._sha256(reference) == project.style_bible.reference_sha256
        )
        checks.append(
            self._result(
                "style_reference_hash",
                reference_ok,
                f"Style reference: {reference}.",
                "Restore the approved reference or create a new style approval.",
            )
        )
        checks.append(
            self._file_check(
                "style_approval_receipt",
                self._resolve(project.style_approval_receipt),
            )
        )
        checks.append(
            self._file_check(
                "production_style_lock",
                self._resolve(project.production_style_lock),
            )
        )
        checks.extend(self._cast_checks(project))
        checks.extend(
            self._model_checks(
                project,
                requirements,
                full_model_hash=full_model_hash,
            )
        )
        for workflow in requirements.get("required_workflows", ()):
            payload, workflow_check = self._load_json(
                workflow,
                name=f"workflow:{workflow}",
            )
            checks.append(workflow_check)
            if payload is not None:
                checks.append(
                    self._result(
                        f"workflow_nodes:{workflow}",
                        self._workflow_has_required_nodes(payload, requirements),
                        "Workflow contains all required production nodes.",
                        "Add the locked IP-Adapter and ControlNet nodes to the workflow.",
                    )
                )
        return checks

    def _cast_checks(self, project: SeriesProject) -> list[SystemHealthCheck]:
        checks: list[SystemHealthCheck] = []
        payload, registry_check = self._load_json(
            project.character_registry,
            name="character_registry",
        )
        checks.append(registry_check)
        if payload is None:
            return checks
        try:
            registry = CharacterRegistry.from_dict(payload)
        except (TypeError, ValueError) as error:
            checks.append(self._fail("character_registry_contract", str(error)))
            return checks
        canonical = tuple(
            member for member in registry.members if member.status == "CANONICAL"
        )
        checks.append(
            self._result(
                "canonical_cast",
                bool(canonical),
                f"Canonical cast members: {len(canonical)}.",
                "Register at least one approved canonical Character Bible.",
            )
        )
        for member in canonical:
            checks.append(
                self._file_check(
                    f"character_bible:{member.character_id}:v{member.version}",
                    self._resolve(member.bible_path),
                )
            )
        return checks

    def _model_checks(
        self,
        project: SeriesProject,
        requirements: dict[str, Any],
        *,
        full_model_hash: bool,
    ) -> list[SystemHealthCheck]:
        checks: list[SystemHealthCheck] = []
        try:
            model_lock = load_model_lock(self._resolve(project.model_lock))
            required = set(requirements.get("required_model_roles", ()))
            available = {entry.role for entry in model_lock.entries}
            missing = sorted(required - available)
            checks.append(
                self._result(
                    "model_roles",
                    not missing,
                    "All required roles are locked."
                    if not missing
                    else f"Missing roles: {missing}.",
                    "Add every required visual model to models.lock.json.",
                )
            )
            for result in verify_model_lock(model_lock, full_hash=full_model_hash):
                checks.append(
                    SystemHealthCheck(
                        name=result.name,
                        status=(
                            "PASS"
                            if result.passed
                            else ("WARN" if result.warning else "FAIL")
                        ),
                        required=not result.warning,
                        details=result.detail,
                        remediation=(
                            None
                            if result.passed
                            else "Install the exact locked model file."
                        ),
                    )
                )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            checks.append(self._fail("model_lock", f"Invalid model lock: {error}"))
        return checks

    def _animation_checks(
        self,
        episode_root: str | Path | None,
        requirements: dict[str, Any],
    ) -> list[SystemHealthCheck]:
        checks: list[SystemHealthCheck] = []
        remote, remote_check = self._load_json(
            requirements.get("required_remote_worker_file", ""),
            name="remote_worker",
        )
        checks.append(remote_check)
        if remote is not None:
            model = requirements.get("model", {})
            remote_ok = (
                remote.get("status") == "READY"
                and int(remote.get("vram_gb", 0))
                >= int(model.get("minimum_vram_gb", 80))
                and remote.get("model_repository") == model.get("repository")
                and bool(str(remote.get("model_revision", "")).strip())
                and bool(str(remote.get("container_image", "")).strip())
                and bool(str(remote.get("persistent_storage", "")).strip())
            )
            checks.append(
                self._result(
                    "remote_worker_contract",
                    remote_ok,
                    (
                        "Remote Wan worker is pinned and ready."
                        if remote_ok
                        else "Remote worker is incomplete or not READY."
                    ),
                    "Create wan2.2-worker.json and pin its image, model revision, storage, and GPU.",
                )
            )
        if episode_root is None:
            checks.append(
                self._fail(
                    "episode_package",
                    "No animation-ready episode package was supplied.",
                    "Pass --episode-root.",
                )
            )
            return checks
        root = self._resolve(episode_root)
        checks.append(
            self._result(
                "episode_root",
                root.is_dir(),
                f"Episode package: {root}.",
                "Create the animation-ready episode package.",
            )
        )
        if not root.is_dir():
            return checks
        for relative in requirements.get("required_episode_files", ()):
            path = root / relative
            checks.append(self._file_check(f"episode_file:{relative}", path))
            if path.suffix.casefold() == ".json" and path.is_file():
                _, json_check = self._load_json(path, name=f"episode_json:{relative}")
                checks.append(json_check)
        for relative in requirements.get("required_episode_directories", ()):
            path = root / relative
            complete = path.is_dir() and any(path.iterdir())
            checks.append(
                self._result(
                    f"episode_directory:{relative}",
                    complete,
                    f"Asset directory: {path}.",
                    "Create the directory and add its approved assets.",
                )
            )
        checks.extend(self._shot_contract_checks(root, requirements))
        return checks

    def _shot_contract_checks(
        self,
        root: Path,
        requirements: dict[str, Any],
    ) -> list[SystemHealthCheck]:
        path = root / "wan-render-manifest.json"
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            shots = payload.get("shots", ()) if isinstance(payload, dict) else ()
            required = set(requirements.get("required_shot_fields", ()))
            allowed = set(requirements.get("allowed_production_methods", ()))
            invalid = [
                str(shot.get("shot_id", index))
                for index, shot in enumerate(shots)
                if not isinstance(shot, dict)
                or not required.issubset(shot)
                or shot.get("production_method") not in allowed
            ]
            return [
                self._result(
                    "wan_shot_contracts",
                    bool(shots) and not invalid,
                    f"Shots: {len(shots)}; invalid: {invalid}.",
                    "Complete every required shot field and use an allowed production method.",
                )
            ]
        except (OSError, json.JSONDecodeError, TypeError) as error:
            return [self._fail("wan_shot_contracts", str(error))]

    def _tool_checks(
        self,
        requirements: dict[str, Any],
        stage: str,
    ) -> list[SystemHealthCheck]:
        key = "required_tools" if stage == VISUAL else "required_local_tools"
        return [
            self._result(
                f"tool:{tool}",
                bool(self._lookup(str(tool))),
                f"Executable lookup for {tool}.",
                f"Install {tool} and expose it on PATH.",
            )
            for tool in requirements.get(key, ())
        ]

    @staticmethod
    def _workflow_has_required_nodes(
        payload: dict[str, Any],
        requirements: dict[str, Any],
    ) -> bool:
        required = set(requirements.get("required_comfyui_nodes", ()))
        raw_nodes = payload.get("nodes")
        nodes = raw_nodes if isinstance(raw_nodes, list) else payload.values()
        available = {
            str(node.get("type") or node.get("class_type"))
            for node in nodes
            if isinstance(node, dict)
        }
        return required.issubset(available)

    def _load_json(
        self,
        path: str | Path,
        *,
        name: str,
    ) -> tuple[dict[str, Any] | None, SystemHealthCheck]:
        target = self._resolve(path)
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("root must be an object")
        except (OSError, json.JSONDecodeError, TypeError) as error:
            return None, self._fail(name, f"Unreadable JSON at {target}: {error}")
        return payload, self._pass(name, f"Loaded {target}.")

    def _file_check(self, name: str, path: Path) -> SystemHealthCheck:
        return self._result(
            name,
            path.is_file(),
            f"Expected file: {path}.",
            "Create or restore the required approved artifact.",
        )

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        return (
            candidate if candidate.is_absolute() else self._root / candidate
        ).resolve()

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _result(
        name: str,
        passed: bool,
        details: str,
        remediation: str,
    ) -> SystemHealthCheck:
        return SystemHealthCheck(
            name=name,
            status="PASS" if passed else "FAIL",
            required=True,
            details=details,
            remediation=None if passed else remediation,
        )

    @staticmethod
    def _pass(name: str, details: str) -> SystemHealthCheck:
        return SystemHealthCheck(name, "PASS", True, details)

    @staticmethod
    def _fail(
        name: str,
        details: str,
        remediation: str = "Resolve this requirement before production.",
    ) -> SystemHealthCheck:
        return SystemHealthCheck(name, "FAIL", True, details, remediation)
