import logging
import asyncio
from typing import Protocol, Any, Sequence
from core.domain.entities.media_asset import MediaAsset
from core.application.ports.cache_port import CachePort
from core.application.services.cache_key_factory import CacheKeyFactory

logger = logging.getLogger(__name__)

class VideoSearchProvider(Protocol):
    async def search(self, query: str, **kwargs: Any) -> list[MediaAsset]:
        """Throws exception on network/timeout errors. Returns [] ONLY for valid empty results."""
        ...

class SearchCacheService:
    """
    Decorator for VideoSearchProvider to add caching transparently.
    
    PRECONDITION: MediaAsset objects MUST be strictly immutable (e.g., frozen dataclasses).
    This service returns new lists (copy-on-read) to prevent cache structure mutation,
    but relies on the immutability of the inner elements to prevent deep-reference mutations.
    """
    def __init__(
        self, 
        provider: VideoSearchProvider, 
        cache: CachePort[Sequence[MediaAsset]],
        provider_name: str = "aggregate",
        default_ttl: int = 3600,
        negative_ttl: int = 60
    ):
        self._provider = provider
        self._cache = cache
        self._provider_name = provider_name
        self._default_ttl = default_ttl
        self._negative_ttl = negative_ttl
        
    async def search(self, query: str, **kwargs: Any) -> list[MediaAsset]:
        cache_key = CacheKeyFactory.generate(self._provider_name, query, **kwargs)
        
        try:
            cached_result = await self._cache.get(cache_key)
            if cached_result is not None:
                logger.debug("Cache hit for key: %s", cache_key)
                return list(cached_result)
        except asyncio.CancelledError:
            raise  # Strictly propagate event loop cancellation
        except Exception:
            logger.exception("Failed to read from cache for key: %s. Bypassing.", cache_key)
            
        logger.debug("Cache miss for key: %s", cache_key)
        
        # Valid empty results return [], timeouts raise exceptions natively.
        results = await self._provider.search(query, **kwargs)
        
        ttl = self._default_ttl if results else self._negative_ttl
        
        try:
            await self._cache.set(cache_key, tuple(results), ttl)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to write to cache for key: %s. Ignoring.", cache_key)
            
        return results
