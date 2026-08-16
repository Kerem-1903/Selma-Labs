from __future__ import annotations

import pytest

from infrastructure.providers.audio.local_audio_inbox import LocalAudioInbox


@pytest.mark.asyncio
async def test_claim_moves_audio_to_processing_and_completion_archives_it(tmp_path):
    source = tmp_path / "chorus.mp3"
    source.write_bytes(b"licensed-audio")
    inbox = LocalAudioInbox(tmp_path)

    job = await inbox.claim_next()

    assert job is not None
    assert source.exists() is False
    assert job.source_uri.endswith(".mp3")
    await inbox.mark_completed(job)

    assert (tmp_path / "completed" / f"{job.job_id}.mp3").is_file()
    assert await inbox.claim_next() is None


@pytest.mark.asyncio
async def test_failed_job_is_retried_then_quarantined_after_budget(tmp_path):
    source = tmp_path / "unstable.wav"
    source.write_bytes(b"licensed-audio")
    inbox = LocalAudioInbox(tmp_path, max_attempts=2)

    first_job = await inbox.claim_next()
    assert first_job is not None
    await inbox.mark_failed(first_job, "temporary provider outage")

    second_job = await inbox.claim_next()
    assert second_job is not None
    assert second_job.job_id == first_job.job_id
    assert second_job.attempts == 1
    await inbox.mark_failed(second_job, "persistent provider outage")

    assert (tmp_path / "failed" / f"{first_job.job_id}.wav").is_file()
    assert await inbox.claim_next() is None
