from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from core.application.services.rig_validation_service import RigValidationService
from core.domain.exceptions import BlenderNotFoundError
from infrastructure.providers.blender.blender_binary_resolver import (
    BlenderBinaryResolver,
)
from infrastructure.providers.blender.blender_rig_adapter import BlenderRigAdapter


def _blender_binary() -> str:
    try:
        return BlenderBinaryResolver.resolve()
    except BlenderNotFoundError:
        pytest.skip("Blender is not installed in this environment.")


@pytest.mark.blender_integration
def test_real_blender_a9_validation_and_preview(tmp_path):
    blender = _blender_binary()
    builder = (
        Path(__file__).resolve().parents[2]
        / "infrastructure"
        / "scripts"
        / "blender"
        / "create_a9_rig_fixture.py"
    )
    model = tmp_path / "akira-a9-smoke.blend"
    preview = tmp_path / "akira-a9-smoke.mp4"

    subprocess.run(
        [
            blender,
            "-b",
            "--factory-startup",
            "--disable-autoexec",
            "--python-exit-code",
            "1",
            "-P",
            str(builder),
            "--",
            "--output",
            str(model),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )

    adapter = BlenderRigAdapter(blender_bin_path=blender, timeout_seconds=120)
    report = asyncio.run(
        RigValidationService(adapter).validate_character_rig(str(model))
    )

    assert report.is_valid is True, report.errors
    rendered = asyncio.run(
        adapter.bake_action_preview(str(model), "IDLE_BREATHING", str(preview), fps=24)
    )
    assert Path(rendered).is_file()
    assert Path(rendered).stat().st_size > 0
