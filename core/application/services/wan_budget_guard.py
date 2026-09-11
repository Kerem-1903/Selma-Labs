from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class WanBudgetGuard:
    """Concurrency-safe cap on newly started attempts during one coordinator run."""

    max_started_attempts: int | None = None
    _started: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_started_attempts is not None and self.max_started_attempts < 0:
            raise ValueError("Wan attempt budget cannot be negative.")

    async def reserve(self) -> bool:
        async with self._lock:
            if self.max_started_attempts is not None and self._started >= self.max_started_attempts:
                return False
            self._started += 1
            return True

    @property
    def started_attempts(self) -> int:
        return self._started

