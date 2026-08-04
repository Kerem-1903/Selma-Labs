from typing import Protocol, TypeVar, Generic
from dataclasses import dataclass

T = TypeVar('T')

@dataclass(frozen=True)
class CacheMetrics:
    hit_count: int
    miss_count: int
    eviction_count: int
    entry_count: int
    dictionary_overhead_bytes: int

    @property
    def hit_rate(self) -> float:
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0

    @property
    def miss_rate(self) -> float:
        return 1.0 - self.hit_rate

class CachePort(Protocol[T]):
    async def get(self, key: str) -> T | None:
        """Retrieves a value from the cache."""
        ...
        
    async def set(self, key: str, value: T, ttl_seconds: int) -> None:
        """Sets a value in the cache with a time-to-live."""
        ...
        
    async def invalidate(self, key: str) -> None:
        """Removes a specific key from the cache."""
        ...
        
    async def invalidate_by_prefix(self, prefix: str) -> None:
        """Removes all keys starting with the specified prefix (Mapped to Redis SCAN)."""
        ...
        
    async def clear(self) -> None:
        """Clears the entire cache."""
        ...
        
    async def get_metrics(self) -> CacheMetrics:
        """Returns cache operational metrics."""
        ...
