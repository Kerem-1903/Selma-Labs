from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.domain.value_objects.render_profile import RenderProfile
from core.domain.value_objects.shot_production_attempt import (
    ProductionAttemptStatus,
    ShotProductionAttempt,
)
from infrastructure.repositories.local_json_shot_production_attempt_repository import (
    LocalJsonShotProductionAttemptRepository,
)


@pytest.mark.asyncio
async def test_attempts_are_persisted_and_loaded_in_order(tmp_path):
    repository = LocalJsonShotProductionAttemptRepository(tmp_path)
    now = datetime.now(timezone.utc)
    attempt = ShotProductionAttempt(
        shot_contract_id="shot-1",
        attempt_number=1,
        profile=RenderProfile.DRAFT,
        provider="fake:i2v",
        seed=1903,
        started_at=now,
        finished_at=now,
        elapsed_seconds=2.5,
        estimated_cost_usd=0.001,
        status=ProductionAttemptStatus.SUCCEEDED,
    )

    await repository.save(attempt)

    assert await repository.list_for_shot("shot-1") == [attempt]
    assert "schema_version" in (tmp_path / "shot-1.json").read_text("utf-8")
