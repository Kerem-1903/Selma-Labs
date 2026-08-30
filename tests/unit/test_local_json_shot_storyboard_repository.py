import json

import pytest

from core.domain.entities.shot_storyboard import ShotStoryboard
from core.domain.exceptions import ShotStoryboardNotFoundError, ShotStoryboardStateError
from infrastructure.repositories.local_json_shot_storyboard_repository import (
    LocalJsonShotStoryboardRepository,
)


@pytest.mark.asyncio
async def test_repository_round_trips_versioned_storyboard_json(tmp_path):
    repository = LocalJsonShotStoryboardRepository(tmp_path)
    storyboard = ShotStoryboard.create("shot-1")

    await repository.save(storyboard)
    restored = await repository.load(storyboard.id)

    assert restored == storyboard
    envelope = json.loads((tmp_path / f"{storyboard.id}.json").read_text("utf-8"))
    assert envelope["schema_version"] == 1
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.asyncio
async def test_repository_reports_missing_and_corrupt_json(tmp_path):
    repository = LocalJsonShotStoryboardRepository(tmp_path)
    with pytest.raises(ShotStoryboardNotFoundError):
        await repository.load("missing")

    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    with pytest.raises(ShotStoryboardStateError):
        await repository.load("broken")
