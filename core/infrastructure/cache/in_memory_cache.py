import time
import asyncio
import sys
from collections import OrderedDict
from typing import TypeVar, Generic
from dataclasses import dataclass
from core.application.ports.cache_port import CachePort, CacheMetrics

T = TypeVar('T')

@dataclass(frozen=True)
class CacheEntry(Generic[T]):
    value: T
    expires_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

class InMemoryCache(CachePort[T]):
    def __init__(self, *, max_entries: int = 1000):
        if max_entries <= 0:
            raise ValueError("max_entries must be greater than zero")
        self._store: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._max_entries = max_entries
        # NOTE: Must be instantiated within an active event loop context.
        self._lock = asyncio.Lock()
        self._hit_count = 0
        self._miss_count = 0
        self._eviction_count = 0

    async def get(self, key: str) -> T | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._miss_count += 1
                return None
            
            if entry.is_expired:
                del self._store[key]
                self._eviction_count += 1
                self._miss_count += 1
                return None
                
            self._hit_count += 1
            self._store.move_to_end(key)
            return entry.value

    async def set(self, key: str, value: T, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be greater than 0, got {ttl_seconds}")
            
        async with self._lock:
            now = time.time()
            expired_keys = [
                key for key, entry in self._store.items()
                if now > entry.expires_at
            ]
            for expired_key in expired_keys:
                del self._store[expired_key]
                self._eviction_count += 1
            if key in self._store:
                del self._store[key]
            elif len(self._store) >= self._max_entries:
                self._store.popitem(last=False)
                self._eviction_count += 1
            self._store[key] = CacheEntry(
                value=value,
                expires_at=now + ttl_seconds
            )

    async def invalidate(self, key: str) -> None:
        async with self._lock:
            if key in self._store:
                del self._store[key]
                self._eviction_count += 1

    async def invalidate_by_prefix(self, prefix: str) -> None:
        async with self._lock:
            keys_to_delete = [k for k in self._store.keys() if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._store[k]
                self._eviction_count += 1

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            self._eviction_count = 0
            self._hit_count = 0
            self._miss_count = 0

    async def get_metrics(self) -> CacheMetrics:
        """
        Returns approximate cache operational metrics.
        Lock-free by design to prevent contention on monitoring threads.
        GIL ensures atomic reads for len() and ints, yielding a safe approximate snapshot.
        """
        return CacheMetrics(
            hit_count=self._hit_count,
            miss_count=self._miss_count,
            eviction_count=self._eviction_count,
            entry_count=len(self._store),
            dictionary_overhead_bytes=sys.getsizeof(self._store)
        )

    async def cleanup_expired(self) -> None:
        """
        Active background cleanup. 
        Must be scheduled by an external Cron/Background Worker.
        """
        async with self._lock:
            now = time.time()
            keys_to_delete = [k for k, v in self._store.items() if now > v.expires_at]
            for k in keys_to_delete:
                del self._store[k]
                self._eviction_count += 1
