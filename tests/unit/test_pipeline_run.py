from __future__ import annotations

import uuid
from types import MappingProxyType

import pytest

from core.domain.entities.pipeline_run import PipelineRun, PipelineRunStatus
from core.domain.exceptions import PipelineRunStateError


def test_pipeline_run_records_stage_artifacts_and_round_trips():
    run = PipelineRun.create(max_retries=2)
    run.bind_input_fingerprint("a" * 64)
    uuid.UUID(run.run_id)

    run.begin_stage("AUDIO_ANALYSIS")
    run.mark_stage_completed("AUDIO_ANALYSIS", {"audio_asset_id": "audio-1"})
    restored = PipelineRun.from_dict(run.to_dict())

    assert restored.status is PipelineRunStatus.RUNNING
    assert restored.input_fingerprint == "a" * 64
    assert restored.get_stage_artifact("AUDIO_ANALYSIS") == {"audio_asset_id": "audio-1"}


def test_failed_run_consumes_retry_only_when_restarted():
    run = PipelineRun.create(max_retries=1)
    run.begin_stage("VISION_SEARCH")
    run.mark_failed("Pexels timeout")

    assert run.can_retry() is True
    assert run.retry_count == 0

    run.begin_stage("VISION_SEARCH")

    assert run.status is PipelineRunStatus.RUNNING
    assert run.retry_count == 1


def test_failed_run_retry_budget_can_be_explicitly_extended():
    run = PipelineRun.create(max_retries=1)
    run.begin_stage("VISION_SEARCH")
    run.mark_failed("provider unavailable")
    run.begin_stage("VISION_SEARCH")
    run.mark_failed("provider unavailable")
    assert run.can_retry() is False

    run.extend_retry_budget(2)

    assert run.max_retries == 3
    assert run.can_retry() is True


def test_completed_run_can_reprocess_downstream_stages_without_losing_upstream():
    run = PipelineRun.create(max_retries=2)
    run.begin_stage("FACT_CHECK")
    run.mark_stage_completed("FACT_CHECK", {"verified": True})
    run.begin_stage("VISION_SEARCH")
    run.mark_stage_completed("VISION_SEARCH", {"clips": ["one.mp4"]})
    run.begin_stage("RENDER")
    run.mark_stage_completed("RENDER", {"output": "old.mp4"})
    run.mark_completed()

    run.reopen_with_invalidated_stages(["VISION_SEARCH", "RENDER", "UPLOAD_PACKAGE"])

    assert run.status is PipelineRunStatus.FAILED
    assert run.get_stage_artifact("FACT_CHECK") == {"verified": True}
    assert run.has_completed_stage("VISION_SEARCH") is False
    assert run.has_completed_stage("RENDER") is False


def test_completed_run_cannot_start_another_stage():
    run = PipelineRun.create()
    run.begin_stage("RENDER")
    run.mark_completed()

    with pytest.raises(PipelineRunStateError, match="completed"):
        run.begin_stage("PUBLISH")


def test_artifact_manifest_is_a_deep_immutable_snapshot():
    run = PipelineRun.create()
    run.begin_stage("AUDIO_ANALYSIS")
    run.mark_stage_completed("AUDIO_ANALYSIS", {"timings": [{"start_ms": 10}]})

    manifest = run.artifact_manifest

    assert isinstance(manifest, MappingProxyType)
    with pytest.raises(TypeError):
        manifest["RENDER"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        manifest["AUDIO_ANALYSIS"]["timings"][0]["start_ms"] = 999
    assert run.get_stage_artifact("AUDIO_ANALYSIS")["timings"][0]["start_ms"] == 10


def test_pipeline_run_rejects_a_different_bound_input():
    run = PipelineRun.create()
    run.bind_input_fingerprint("a" * 64)

    with pytest.raises(PipelineRunStateError, match="do not match"):
        run.bind_input_fingerprint("b" * 64)


def test_legacy_run_with_artifacts_cannot_adopt_unknown_input():
    run = PipelineRun.create()
    run.begin_stage("SCRIPT_GENERATION")
    run.mark_stage_completed("SCRIPT_GENERATION", {"script": {"topic": "old"}})

    with pytest.raises(PipelineRunStateError, match="legacy"):
        run.bind_input_fingerprint("a" * 64)


def test_explicit_reprocess_can_rebind_configuration_fingerprint():
    run = PipelineRun.create()
    run.bind_input_fingerprint("a" * 64)
    run.begin_stage("RENDER")
    run.mark_stage_completed("RENDER", {"path": "old.mp4"})
    run.mark_completed()
    run.reopen_with_invalidated_stages(["RENDER"])

    run.rebind_input_fingerprint_after_reprocess("b" * 64)

    assert run.input_fingerprint == "b" * 64
