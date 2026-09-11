from __future__ import annotations

from abc import ABC, abstractmethod


class WanComputeLifecyclePort(ABC):
    """Narrow lifecycle capability; it must not expose account-wide credentials."""

    @property
    @abstractmethod
    def provider_auto_stop_enabled(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def stop_own_instance(self) -> None:
        """Stop only the worker instance represented by this adapter."""
        raise NotImplementedError

