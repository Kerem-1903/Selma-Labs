from __future__ import annotations

import pytest

from infrastructure.providers.render.remotion_render_provider import RemotionRenderProvider


def test_rejects_invalid_timeout():
    with pytest.raises(ValueError, match="subprocess_timeout_seconds"):
        RemotionRenderProvider(subprocess_timeout_seconds=0)


def test_uses_local_project_cli(tmp_path):
    project = tmp_path / "motion"
    provider = RemotionRenderProvider(project_directory=str(project))

    assert provider._project == project.resolve()
    assert provider._cli == (
        project / "node_modules" / ".bin" / "remotion.cmd"
    ).resolve()


def test_stages_local_media_without_copying_when_hardlinks_are_available(tmp_path):
    source = tmp_path / "octopus.mp4"
    source.write_bytes(b"video")
    props = tmp_path / "timeline.json"
    props.write_text(
        '{"scenes":[{"source":"' + source.resolve().as_uri() + '"}]}',
        encoding="utf-8",
    )

    staged_props, public_directory = RemotionRenderProvider._stage_props(
        props,
        tmp_path / "work",
    )

    assert (public_directory / "clip-000.mp4").read_bytes() == b"video"
    assert '"source": "clip-000.mp4"' in staged_props.read_text(encoding="utf-8")
