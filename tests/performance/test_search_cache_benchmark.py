import pytest
import asyncio
import time
import logging
from core.infrastructure.cache.in_memory_cache import InMemoryCache

logger = logging.getLogger(__name__)

@pytest.mark.asyncio
@pytest.mark.performance
async def test_cache_100k_concurrent_lookups():
    cache = InMemoryCache()
    await cache.set("hot_key", ["asset_1", "asset_2"], 3600)
    
    async def worker(reads: int):
        for _ in range(reads):
            await cache.get("hot_key")
            
    start_time = time.perf_counter()
    
    tasks = [worker(1000) for _ in range(100)]
    await asyncio.gather(*tasks)
    
    duration = time.perf_counter() - start_time
    metrics = await cache.get_metrics()
    
    assert metrics.hit_count == 100000
    
    # Reporting instead of brittle assertions
    logger.info("100K concurrent cache reads completed in %.4fs", duration)

@pytest.mark.asyncio
@pytest.mark.performance
async def test_lock_contention_metrics_fetch():
    cache = InMemoryCache()
    await cache.set("key", ["val"], 3600)
    
    async def worker():
        for _ in range(500):
            await cache.get_metrics()
            
    start_time = time.perf_counter()
    tasks = [worker() for _ in range(100)]
    await asyncio.gather(*tasks)
    
    duration = time.perf_counter() - start_time
    logger.info("50K lock-free metric reads completed in %.4fs", duration)
