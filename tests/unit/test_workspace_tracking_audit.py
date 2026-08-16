from scripts.audit_workspace_tracking import _category


def test_classifies_source_and_configuration_as_protected():
    assert _category("core/application/service.py") == "source"
    assert _category("motion/src/Root.tsx") == "source"
    assert _category(".github/workflows/quality-gates.yml") == "configuration"


def test_classifies_generated_and_reference_files_as_local_only():
    assert _category(".selma_runs-smoke/run.json") == "generated_output"
    assert _category(".codex_video_review/frame.jpg") == "generated_output"
    assert _category("reference/source-video.mp4") == "local_reference"


def test_classifies_production_media_for_lfs():
    assert _category("assets/visuals/planet.mp4") == "production_media_lfs"
    assert _category("motion/public/topic/narration.mp3") == "production_media_lfs"
    assert _category("assets/brand/logo.svg") == "production_image_asset"
