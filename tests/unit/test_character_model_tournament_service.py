from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.application.services.character_model_tournament_service import (
    CharacterModelTournamentService,
)
from core.domain.value_objects.character_creation_brief import CharacterCreationBrief
from core.domain.value_objects.character_design import (
    CharacterDesignCandidate,
    CharacterDesignCandidatePack,
)

ROOT = Path(__file__).parents[2]


class _DesignService:
    def __init__(self, calls: list[dict[str, object]]) -> None:
        self._calls = calls

    async def generate_candidates(self, brief, **kwargs):
        self._calls.append({"brief_hash": brief.content_hash, **kwargs})
        return CharacterDesignCandidatePack(
            schema_version=1,
            character_id=brief.character_id,
            brief_hash=brief.content_hash,
            run_id=str(kwargs["run_id"]),
            candidates=(
                CharacterDesignCandidate(
                    storage_key="candidate.png",
                    content_hash="a" * 64,
                    seed=1,
                    provider="fake:test",
                    provider_asset_id="candidate",
                    width=1024,
                    height=1024,
                    run_id=str(kwargs["run_id"]),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_tournament_uses_same_text_only_seed_inputs_for_both_models():
    calls: list[dict[str, object]] = []
    locks_seen = []

    def factory(model_lock_path):
        locks_seen.append(model_lock_path)
        return _DesignService(calls)

    raw_brief = json.loads(
        (ROOT / "assets/character_creation_briefs/kaito.json").read_text(
            encoding="utf-8"
        )
    )
    brief = CharacterCreationBrief.from_dict(raw_brief)
    async def release():
        return None

    service = CharacterModelTournamentService(ROOT, factory, release)
    report = await service.run(
        benchmark_path=ROOT / "config/character_benchmarks/akira-quality-v1.json",
        brief=brief,
        model_lock_paths=(
            ROOT / "models.lock.json",
            ROOT / "config/model_profiles/illustrious-xl-v2.lock.json",
        ),
        count=3,
        run_id="test-round",
    )

    assert report["generation_mode"] == "text_only"
    assert report["identity_reference_used"] is False
    assert len(report["variants"]) == 2
    assert len(calls) == 2
    assert {call["count"] for call in calls} == {3}
    assert all("style_reference_path" not in call for call in calls)
    assert len(set(locks_seen)) == 2


@pytest.mark.asyncio
async def test_tournament_accepts_dedicated_full_body_benchmark_brief():
    calls: list[dict[str, object]] = []

    def factory(model_lock_path):
        return _DesignService(calls)

    raw_brief = json.loads(
        (ROOT / "assets/character_creation_briefs/kaito-quality-benchmark-v1.json")
        .read_text(encoding="utf-8")
    )
    brief = CharacterCreationBrief.from_dict(raw_brief)

    async def release():
        return None

    service = CharacterModelTournamentService(ROOT, factory, release)
    report = await service.run(
        benchmark_path=ROOT / "config/character_benchmarks/akira-quality-v1.json",
        brief=brief,
        model_lock_paths=(
            ROOT / "models.lock.json",
            ROOT / "config/model_profiles/illustrious-xl-v2.lock.json",
        ),
        count=1,
        run_id="dedicated-benchmark",
    )

    assert report["status"] == "PENDING_HUMAN_REVIEW"
    assert report["character_id"] == "kaito"
    assert len(report["variants"]) == 2
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_tournament_requires_two_distinct_checkpoints():
    raw_brief = json.loads(
        (ROOT / "assets/character_creation_briefs/kaito.json").read_text(
            encoding="utf-8"
        )
    )
    brief = CharacterCreationBrief.from_dict(raw_brief)
    async def release():
        return None

    service = CharacterModelTournamentService(
        ROOT, lambda _lock: _DesignService([]), release
    )

    with pytest.raises(ValueError, match="duplicate checkpoint"):
        await service.run(
            benchmark_path=ROOT
            / "config/character_benchmarks/akira-quality-v1.json",
            brief=brief,
            model_lock_paths=(ROOT / "models.lock.json", ROOT / "models.lock.json"),
            count=1,
            run_id="duplicate",
        )


@pytest.mark.asyncio
async def test_tournament_rejects_face_brief_for_full_body_benchmark_before_factory():
    raw_brief = json.loads(
        (ROOT / "assets/character_creation_briefs/kaito-v4.json").read_text(
            encoding="utf-8"
        )
    )
    brief = CharacterCreationBrief.from_dict(raw_brief)
    factory_calls = []

    def factory(model_lock_path):
        factory_calls.append(model_lock_path)
        return _DesignService([])

    async def release():
        return None

    service = CharacterModelTournamentService(ROOT, factory, release)

    with pytest.raises(ValueError, match="requires a full-body character"):
        await service.run(
            benchmark_path=ROOT
            / "config/character_benchmarks/akira-quality-v1.json",
            brief=brief,
            model_lock_paths=(
                ROOT / "models.lock.json",
                ROOT / "config/model_profiles/illustrious-xl-v2.lock.json",
            ),
            count=1,
            run_id="incompatible",
        )

    assert factory_calls == []
