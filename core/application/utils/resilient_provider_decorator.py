import asyncio
import random
import logging
from typing import Any
from core.domain.entities.media_asset import MediaAsset
from core.application.ports.video_search_provider import VideoSearchProvider

logger = logging.getLogger(__name__)

class ProviderRetryExhausted(Exception):
    """Fırlatılan nihai hata, orijinal hatayı (cause) zincirleyerek korur."""
    pass

class ResilientSearchProviderDecorator(VideoSearchProvider):
    """
    VideoSearchProvider'ı Timeout, Retry ve Exponential Backoff (with Jitter) yetenekleriyle sarmalar.
    Yalnızca belirtilen geçici (transient) hataları retry eder.
    """
    def __init__(
        self,
        inner_provider: VideoSearchProvider,
        timeout_seconds: float = 2.0,
        max_retries: int = 2,
        base_delay: float = 0.5,
        max_backoff: float = 30.0,
        retryable_exceptions: tuple[type[Exception], ...] = (asyncio.TimeoutError, ConnectionError),
        rng: random.Random | None = None
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if max_backoff < base_delay:
            raise ValueError("max_backoff cannot be less than base_delay")
            
        if not retryable_exceptions:
            raise ValueError("retryable_exceptions cannot be empty")
        for exc in retryable_exceptions:
            if not isinstance(exc, type) or not issubclass(exc, Exception):
                raise TypeError(f"Expected Exception subclass in retryable_exceptions, got {exc}")
            
        self._inner = inner_provider
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_backoff = max_backoff
        self._retryable_exceptions = retryable_exceptions
        self._rng = rng or random.Random()

    @property
    def name(self) -> str:
        return self._inner.name

    async def search(self, query: str, **kwargs: Any) -> list[MediaAsset]:
        last_exception = None
        
        for attempt in range(self._max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._inner.search(query, **kwargs),
                    timeout=self._timeout_seconds
                )
            except asyncio.CancelledError:
                raise  # Event loop iptallerini asla yutma
            except Exception as e:
                # Yalnızca geçici (transient) hatalar retry edilir (Fail-fast koruması).
                if not isinstance(e, self._retryable_exceptions):
                    logger.error("Provider '%s' failed with non-retryable error: %s", self.name, type(e).__name__)
                    raise
                    
                last_exception = e
                
                # PII (Personally Identifiable Information) sızıntısını önlemek için 'query' loglanmaz.
                logger.warning(
                    "Provider retry triggered. provider=%s, attempt=%d/%d, error=%s", 
                    self.name, attempt + 1, self._max_retries + 1, type(e).__name__
                )
                
                if attempt < self._max_retries:
                    # Exponential Backoff + Upper Bound + Injected Jitter
                    delay = min(self._max_backoff, self._base_delay * (2 ** attempt))
                    jitter = self._rng.uniform(0, delay * 0.2)
                    await asyncio.sleep(delay + jitter)
                    
        logger.error("Provider '%s' exhausted all %d retries.", self.name, self._max_retries)
        raise ProviderRetryExhausted(f"Provider '{self.name}' failed after {self._max_retries} retries.") from last_exception
