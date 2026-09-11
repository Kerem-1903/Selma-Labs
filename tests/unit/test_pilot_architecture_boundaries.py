from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
PILOT_APPLICATION_MODULES = (
    "core/application/services/animatic_render_service.py",
    "core/application/services/character_model_tournament_service.py",
    "core/application/services/episode_asset_generation_service.py",
    "core/application/services/system_health_service.py",
    "core/application/services/trailer_animatic_service.py",
    "core/application/services/wan_worker_service.py",
)


def test_pilot_application_services_do_not_import_outer_layers():
    violations: list[str] = []
    for relative_path in PILOT_APPLICATION_MODULES:
        path = ROOT / relative_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        for node in ast.walk(tree):
            names: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = (node.module,)
            for name in names:
                if name == "config" or name.startswith(("config.", "infrastructure.")):
                    violations.append(f"{relative_path}:{node.lineno} imports {name}")

    assert violations == []
