import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch
from core.domain.entities.media_asset import MediaAsset
from core.application.services.cache_key_factory import CacheKeyFactory
from core.infrastructure.cache.in_memory_cache import InMemoryCache
from core.application.services.search_cache_service import SearchCacheService

def dummy_asset(aid: str) -> MediaAsset:
    return MediaAsset(id=aid, provider="test", media_type="video")

def test_cache_key_type_safety_and_determinism():
    # 1 vs "1" should NOT collide
    key1 = CacheKeyFactory.generate("test", "query", page=1)
    key2 = CacheKeyFactory.generate("test", "query", page="1")
    assert key1 != key2
    
    # Order independence
    key3 = CacheKeyFactory.generate("test", "q", a=1, b=2)
    key4 = CacheKeyFactory.generate("test", "q", b=2, a=1)
    assert key3 == key4

@pytest.mark.asyncio
async def test_invalid_ttl_raises_error():
    cache = InMemoryCache()
    with pytest.raises(ValueError, match="ttl_seconds must be greater than 0"):
        await cache.set("key", ["val"], 0)
    with pytest.raises(ValueError):
        await cache.set("key", ["val"], -5)

@pytest.mark.asyncio
async def test_in_memory_cache_ttl_expiration():
    cache = InMemoryCache()
    await cache.set("test_key", ["val"], ttl_seconds=1)
    
    assert await cache.get("test_key") == ["val"]
    
    with patch("time.time", return_value=time.time() + 2):
        assert await cache.get("test_key") is None
        metrics = await cache.get_metrics()
        assert metrics.eviction_count == 1

@pytest.mark.asyncio
async def test_in_memory_cache_invalidation_by_prefix():
    cache = InMemoryCache()
    await cache.set("pexels:water", ["A"], 100)
    await cache.set("pexels:fire", ["B"], 100)
    await cache.set("pixabay:deepwater", ["C"], 100)
    
    # Invalidate prefix
    await cache.invalidate_by_prefix("pexels:")
    assert await cache.get("pexels:water") is None
    assert await cache.get("pixabay:deepwater") == ["C"] # Safe
    
    metrics = await cache.get_metrics()
    assert metrics.eviction_count == 2

@pytest.mark.asyncio
async def test_search_cache_service_hits_and_negative_cache():
    mock_provider = AsyncMock()
    mock_provider.search.return_value = [] # Empty result -> Negative cache trigger
    
    cache = InMemoryCache()
    service = SearchCacheService(
        provider=mock_provider, 
        cache=cache, 
        provider_name="test",
        default_ttl=3600,
        negative_ttl=5
    )
    
    # First call (Miss)
    results1 = await service.search("empty query", page=1)
    assert results1 == []
    assert mock_provider.search.call_count == 1
    
    # Second call (Hit)
    results2 = await service.search("empty query", page=1)
    assert results2 == []
    assert mock_provider.search.call_count == 1 # Provider NOT called again

@pytest.mark.asyncio
async def test_search_cache_service_graceful_degradation_on_cache_failure():
    mock_provider = AsyncMock()
    mock_provider.search.return_value = [dummy_asset("1")]
    
    mock_cache = AsyncMock()
    mock_cache.get.side_effect = Exception("Redis Connection Error")
    mock_cache.set.side_effect = Exception("Redis Write Error")
    
    service = SearchCacheService(mock_provider, mock_cache)
    
    # Should NOT raise exception, must return provider data gracefully
    results = await service.search("query")
    assert len(results) == 1
    assert mock_provider.search.call_count == 1

@pytest.mark.asyncio
async def test_cancelled_error_is_propagated():
    mock_provider = AsyncMock()
    mock_cache = AsyncMock()
    mock_cache.get.side_effect = asyncio.CancelledError()
    
    service = SearchCacheService(mock_provider, mock_cache)
    
    with pytest.raises(asyncio.CancelledError):
        await service.search("query")
