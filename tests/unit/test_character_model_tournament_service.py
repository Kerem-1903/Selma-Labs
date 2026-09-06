from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.settings import Settings
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


class _Container:
    def __init__(self, calls: list[dict[str, object]]) -> None:
        self.character_design_service = _DesignService(calls)


@pytest.mark.asyncio
async def test_tournament_uses_same_text_only_seed_inputs_for_both_models():
    calls: list[dict[str, object]] = []
    settings_seen = []

    def factory(*, settings):
        settings_seen.append(settings)
        return _Container(calls)

    raw_brief = json.loads(
        (ROOT / "assets/character_creation_briefs/kaito.json").read_text(
            encoding="utf-8"
        )
    )
    brief = CharacterCreationBrief.from_dict(raw_brief)
    service = CharacterModelTournamentService(ROOT, factory)

    async def release(_api_url):
        return None

    service._release_comfy_memory = release
    report = await service.run(
        benchmark_path=ROOT / "config/character_benchmarks/akira-quality-v1.json",
        brief=brief,
        model_lock_paths=(
            ROOT / "models.lock.json",
            ROOT / "config/model_profiles/illustrious-xl-v2.lock.json",
        ),
        count=3,
        run_id="test-round",
        base_settings=Settings(),
    )

    assert report["generation_mode"] == "text_only"
    assert report["identity_reference_used"] is False
    assert len(report["variants"]) == 2
    assert len(calls) == 2
    assert {call["count"] for call in calls} == {3}
    assert all("style_reference_path" not in call for call in calls)
    assert len({setting.comfyui_model_lock_path for setting in settings_seen}) == 2


@pytest.mark.asyncio
async def test_tournament_requires_two_distinct_checkpoints():
    raw_brief = json.loads(
        (ROOT / "assets/character_creation_briefs/kaito.json").read_text(
            encoding="utf-8"
        )
    )
    brief = CharacterCreationBrief.from_dict(raw_brief)
    service = CharacterModelTournamentService(ROOT, lambda **_: _Container([]))

    with pytest.raises(ValueError, match="duplicate checkpoint"):
        await service.run(
            benchmark_path=ROOT
            / "config/character_benchmarks/akira-quality-v1.json",
            brief=brief,
            model_lock_paths=(ROOT / "models.lock.json", ROOT / "models.lock.json"),
            count=1,
            run_id="duplicate",
            base_settings=Settings(),
        )
