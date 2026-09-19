from __future__ import annotations

import asyncio

from core.application.services.animatic_render_service import AnimaticRenderService
from core.application.services.episode_animatic_service import EpisodeAnimaticService
from core.application.services.episode_director_service import EpisodeDirectorService
from infrastructure.storage.local_fs_storage import LocalFsStorage


def _plan():
    return EpisodeDirectorService().plan_text(
        "SCENE: Rooftop\nAKIRA: We move now.", episode_id="render-test"
    )


def test_strict_mode_blocks_before_render_and_placeholder_mode_keeps_frames(tmp_path):
    storage = LocalFsStorage(str(tmp_path / "storage"))
    service = EpisodeAnimaticService(storage)

    strict = asyncio.run(service.build(_plan(), mode="STRICT"))
    placeholder = asyncio.run(service.build(_plan(), mode="PLACEHOLDER"))

    assert strict.status == "BLOCKED"
    assert strict.project is None
    assert placeholder.status == "READY_FOR_REVIEW"
    assert placeholder.project is not None
    assert placeholder.project.duration_in_frames == 96
    assert all(clip.warning for clip in placeholder.project.clips)


class _FailingInspector:
    async def inspect(self, path: str):
        raise RuntimeError("invalid mp4")


def test_render_failure_preserves_existing_output(tmp_path):
    output = tmp_path / "animatic.mp4"
    output.write_bytes(b"previous-valid-output")
    service = AnimaticRenderService(
        motion_directory=tmp_path,
        inspector=_FailingInspector(),
        timeout_seconds=1,
    )
    result = asyncio.run(
        service.render(_placeholder_project(tmp_path), props_path=tmp_path / "props.json", output_path=output)
    )
    assert result.status == "FAILED"
    assert output.read_bytes() == b"previous-valid-output"


def test_render_failure_never_publishes_output(tmp_path):
    output = tmp_path / "animatic.mp4"
    service = AnimaticRenderService(
        motion_directory=tmp_path,
        inspector=_FailingInspector(),
        timeout_seconds=1,
    )

    result = asyncio.run(
        service.render(
            # The command fails before inspection because this temporary motion
            # directory has no package; this still verifies atomic failure state.
            _placeholder_project(tmp_path),
            props_path=tmp_path / "props.json",
            output_path=output,
        )
    )

    assert result.status == "FAILED"
    assert not output.exists()


def _placeholder_project(tmp_path):
    from core.domain.entities.animatic_project import AnimaticClip, AnimaticProject

    return AnimaticProject.create(
        production_plan_id="render-test",
        clips=(
            AnimaticClip(
                shot_id="render-shot-001",
                start_frame=0,
                duration_frames=240,
                image_storage_key="placeholder://render-shot-001/visual",
                warning="MISSING VISUAL ASSET",
            ),
        ),
    )
