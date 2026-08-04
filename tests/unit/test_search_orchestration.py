import pytest
import asyncio
import random
from unittest.mock import AsyncMock, patch
from core.domain.entities.media_asset import MediaAsset
from core.application.utils.resilient_provider_decorator import ResilientSearchProviderDecorator, ProviderRetryExhausted
from core.application.services.search_orchestrator_service import SearchOrchestratorService

def dummy_asset(aid: str, provider: str = "test") -> MediaAsset:
    return MediaAsset(id=aid, provider=provider, media_type="video")

@pytest.mark.asyncio
async def test_resilient_decorator_retries_and_succeeds():
    mock_inner = AsyncMock()
    mock_inner.name = "flaky_provider"
    
    mock_inner.search.side_effect = [
        ConnectionError("Network Blip"),
        TimeoutError("Slow API"),
        [dummy_asset("1")]
    ]
    
    resilient_provider = ResilientSearchProviderDecorator(
        mock_inner, timeout_seconds=1.0, max_retries=2, base_delay=0.01,
        retryable_exceptions=(ConnectionError, TimeoutError)
    )
    
    result = await resilient_provider.search("query")
    
    assert len(result) == 1
    assert mock_inner.search.call_count == 3 

@pytest.mark.asyncio
async def test_resilient_decorator_exhausts_retries():
    mock_inner = AsyncMock()
    mock_inner.name = "dead_provider"
    mock_inner.search.side_effect = ConnectionError("Permanent Failure")
    
    resilient_provider = ResilientSearchProviderDecorator(
        mock_inner, timeout_seconds=1.0, max_retries=1, base_delay=0.01,
        retryable_exceptions=(ConnectionError,)
    )
    
    with pytest.raises(ProviderRetryExhausted) as exc_info:
        await resilient_provider.search("query")
        
    assert isinstance(exc_info.value.__cause__, ConnectionError)
    assert mock_inner.search.call_count == 2 

@pytest.mark.asyncio
async def test_non_retryable_exception_fails_fast():
    class AuthenticationError(Exception): pass
    
    mock_inner = AsyncMock()
    mock_inner.name = "auth_fail_provider"
    mock_inner.search.side_effect = AuthenticationError("Invalid API Key")
    
    resilient_provider = ResilientSearchProviderDecorator(
        mock_inner, retryable_exceptions=(ConnectionError,)
    )
    
    with pytest.raises(AuthenticationError):
        await resilient_provider.search("query")
        
    assert mock_inner.search.call_count == 1 

@pytest.mark.asyncio
@patch("asyncio.sleep") # Testleri yavaşlatmamak için sleep'i mockla
async def test_jitter_is_applied_to_backoff_via_injected_rng(mock_sleep):
    mock_inner = AsyncMock()
    mock_inner.name = "jitter_test"
    mock_inner.search.side_effect = [ConnectionError("Blip"), ConnectionError("Blip"), []]
    
    # RNG'yi DI ile vererek deterministic test yazıyoruz
    mock_rng = random.Random(42)
    with patch.object(mock_rng, 'uniform', return_value=0.1) as mock_uniform:
        resilient_provider = ResilientSearchProviderDecorator(
            mock_inner, max_retries=2, base_delay=1.0, retryable_exceptions=(ConnectionError,), rng=mock_rng
        )
        await resilient_provider.search("query")
        
        assert mock_uniform.call_count == 2
        # 1. Delay = 1.0 + 0.1 = 1.1
        # 2. Delay = 2.0 + 0.1 = 2.1
        mock_sleep.assert_any_call(1.1)
        mock_sleep.assert_any_call(2.1)

@pytest.mark.asyncio
async def test_orchestrator_graceful_degradation_and_deduplication():
    mock_pexel = AsyncMock()
    mock_pexel.name = "pexels"
    mock_pexel.search.return_value = [dummy_asset("1", "pexels"), dummy_asset("2", "pexels")]
    
    mock_pixabay = AsyncMock()
    mock_pixabay.name = "pixabay"
    mock_pixabay.search.side_effect = Exception("Pixabay is down")
    
    mock_unsplash = AsyncMock()
    mock_unsplash.name = "unsplash"
    mock_unsplash.search.return_value = [dummy_asset("2", "unsplash"), dummy_asset("3", "unsplash")]
    
    mock_duplicates = AsyncMock()
    mock_duplicates.name = "dupe"
    mock_duplicates.search.return_value = [dummy_asset("9", "dupe"), dummy_asset("9", "dupe")]

    orchestrator = SearchOrchestratorService([mock_pexel, mock_pixabay, mock_unsplash, mock_duplicates])
    results = await orchestrator.search("nature")
    
    assert len(results) == 5
    assert {a.id for a in results} == {"1", "2", "3", "9"}
    assert sum(1 for a in results if a.id == "9") == 1 

@pytest.mark.asyncio
async def test_orchestrator_handles_edge_case_provider_returns():
    mock_none = AsyncMock(); mock_none.name = "none"; mock_none.search.return_value = None
    mock_str = AsyncMock(); mock_str.name = "str"; mock_str.search.return_value = "error string"
    mock_tuple = AsyncMock(); mock_tuple.name = "tuple"; mock_tuple.search.return_value = (dummy_asset("1"), dummy_asset("2"))
    mock_invalid = AsyncMock(); mock_invalid.name = "invalid"; mock_invalid.search.return_value = [{"id": "bad"}]
    mock_generator = AsyncMock(); mock_generator.name = "gen"; mock_generator.search.return_value = (dummy_asset(str(i)) for i in range(3, 5))

    orchestrator = SearchOrchestratorService([mock_none, mock_str, mock_tuple, mock_invalid, mock_generator])
    results = await orchestrator.search("query")
    
    assert len(results) == 4
    assert {a.id for a in results} == {"1", "2", "3", "4"}

@pytest.mark.asyncio
async def test_orchestrator_empty_provider_list():
    orchestrator = SearchOrchestratorService([])
    assert await orchestrator.search("test") == []
