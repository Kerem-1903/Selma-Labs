import pytest
from core.domain.entities.media_asset import MediaAsset
from core.domain.value_objects.scene import Scene
from core.domain.value_objects.asset_score import AssetScore
from core.domain.value_objects.scored_asset import ScoredAsset
from core.domain.value_objects.selection_context import SelectionContext
from core.application.selection.rules.asset_reuse_rule import AssetReuseRule
from core.application.selection.rules.provider_fatigue_rule import ProviderFatigueRule
from core.application.selection.rules.keyword_fatigue_rule import KeywordFatigueRule
from core.application.services.asset_selection_service import AssetSelectionService
from core.application.selection.selection_rule import SelectionRule

def dummy_asset(aid: str, provider: str, tags: list[str], score: float) -> ScoredAsset:
    return ScoredAsset(
        asset=MediaAsset(id=aid, provider=provider, media_type="video", tags=tags),
        score=AssetScore(final_score=score)
    )

def test_selection_context_immutability():
    ctx1 = SelectionContext()
    asset = MediaAsset(id="1", provider="px", media_type="vid", tags=["A", "B"])

    ctx2 = ctx1.with_asset(asset, provider_window=1, keyword_window=2)

    assert "1" not in ctx1.used_asset_ids
    assert "1" in ctx2.used_asset_ids
    assert ctx2.recent_providers == ("px",)
    assert ctx2.recent_keywords == ("a", "b")

def test_rules_boundaries():
    with pytest.raises(ValueError):
        AssetReuseRule(-0.1)
    with pytest.raises(ValueError):
        ProviderFatigueRule(float("nan"))

def test_asset_selection_service_invalid_top_k():
    with pytest.raises(ValueError, match="top_k must be greater than zero"):
        AssetSelectionService([], top_k=0)
    with pytest.raises(ValueError, match="top_k must be greater than zero"):
        AssetSelectionService([], top_k=-5)

def test_asset_reuse_rule():
    rule = AssetReuseRule(0.8)
    ctx = SelectionContext(used_asset_ids=frozenset(["used_1"]))

    assert rule.calculate_penalty(dummy_asset("used_1", "px", [], 1.0), ctx) == 0.8
    assert rule.calculate_penalty(dummy_asset("new_1", "px", [], 1.0), ctx) == 0.0

def test_fatigue_rules():
    p_rule = ProviderFatigueRule(0.2)
    k_rule = KeywordFatigueRule(0.1)

    ctx = SelectionContext(recent_providers=("pexels", "pexels"), recent_keywords=("city", "city", "night"))

    assert p_rule.calculate_penalty(dummy_asset("1", "pexels", [], 1.0), ctx) == pytest.approx(0.4)
    assert p_rule.calculate_penalty(dummy_asset("2", "pixabay", [], 1.0), ctx) == 0.0

    assert k_rule.calculate_penalty(dummy_asset("3", "px", ["City"], 1.0), ctx) == pytest.approx(0.2)
    assert k_rule.calculate_penalty(dummy_asset("4", "px", ["nature"], 1.0), ctx) == 0.0

def test_asset_selection_service_reranks_and_evolves_context():
    rules = [AssetReuseRule(0.8), ProviderFatigueRule(0.2)]
    service = AssetSelectionService(rules, provider_window=2, keyword_window=0, top_k=5)

    scene1 = Scene(index=1, narration="", search_keywords=[], detected_objects=[], location="", mood="", visual_priority="", start_time=0.0, end_time=1.0)
    scene2 = Scene(index=2, narration="", search_keywords=[], detected_objects=[], location="", mood="", visual_priority="", start_time=1.0, end_time=2.0)

    input_data = [
        (scene1, [dummy_asset("A", "pexels", [], 0.9), dummy_asset("B", "pixabay", [], 0.8)]),
        (scene2, [
            dummy_asset("A", "pexels", [], 0.95),
            dummy_asset("C", "pexels", [], 0.85),
            dummy_asset("D", "pixabay", [], 0.80)
        ])
    ]

    result = service.select_for_timeline(input_data)

    assert result[0][1][0].original.asset.id == "A"
    assert result[1][1][0].original.asset.id == "D"
    assert result[1][1][0].adjusted_score == pytest.approx(0.80)

def test_asset_selection_service_survives_crashing_rule():
    class FaultyRule(SelectionRule):
        def calculate_penalty(self, candidate, context):
            raise Exception("Database failure")

    service = AssetSelectionService([FaultyRule()], 0, 0, top_k=1)
    scene = Scene(index=1, narration="", search_keywords=[], detected_objects=[], location="", mood="", visual_priority="", start_time=0.0, end_time=1.0)

    result = service.select_for_timeline([(scene, [dummy_asset("1", "px", [], 1.0)])])
    assert result[0][1][0].adjusted_score == 1.0

def test_asset_selection_service_zero_allocation_empty_penalties():
    service = AssetSelectionService(rules=[AssetReuseRule(0.5)], provider_window=1, keyword_window=1, top_k=5)
    scene = Scene(index=1, narration="", search_keywords=[], detected_objects=[], location="", mood="", visual_priority="", start_time=0.0, end_time=1.0)

    asset = dummy_asset("A", "pexels", ["nature"], 0.9)
    result = service.select_for_timeline([(scene, [asset])])

    adjusted_score_obj = result[0][1][0]
    # Verify singleton empty penalties mapping is used when no penalties apply
    assert len(adjusted_score_obj.penalties) == 0
    assert adjusted_score_obj.adjusted_score == 0.9
