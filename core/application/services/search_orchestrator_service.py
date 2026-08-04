import logging
import asyncio
from typing import Sequence, Any
from core.domain.entities.media_asset import MediaAsset
from core.application.ports.video_search_provider import VideoSearchProvider

logger = logging.getLogger(__name__)

class SearchOrchestratorService(VideoSearchProvider):
    """
    N adet Provider'a paralel istek atıp (Fan-out), sonuçları birleştiren Orkestratör Servis.
    Hatalara, boş dönenlere ve hatalı tiplere karşı tam dayanıklıdır (Fault Tolerant).
    """
    def __init__(self, providers: Sequence[VideoSearchProvider], orchestrator_name: str = "aggregate"):
        self._providers = tuple(providers)
        self._name = orchestrator_name

    @property
    def name(self) -> str:
        return self._name

    async def search(self, query: str, **kwargs: Any) -> list[MediaAsset]:
        if not self._providers:
            return []

        # 1. FAN-OUT: Tüm provider'lara aynı anda asenkron çağrı at.
        tasks = [provider.search(query, **kwargs) for provider in self._providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 2. FAN-IN & DEDUPLICATION: Sonuçları birleştir.
        seen_keys = set()
        merged_results = []

        for provider, result in zip(self._providers, results):
            if isinstance(result, asyncio.CancelledError):
                raise result  # Sistemsel iptalleri re-raise et.
            
            if isinstance(result, Exception):
                logger.exception("Provider '%s' failed during orchestration.", provider.name, exc_info=result)
                continue

            if result is None:
                continue
                
            # Python 'str' ve 'bytes' iterable'dır. Harf harf listeye dönmesini engelle.
            if isinstance(result, (str, bytes)):
                logger.error("Provider '%s' returned a string/bytes instead of an asset list.", provider.name)
                continue
                
            if not isinstance(result, list):
                try:
                    result = list(result)
                except TypeError:
                    logger.error("Provider '%s' returned non-iterable data type: %s", provider.name, type(result))
                    continue

            for asset in result:
                if not isinstance(asset, MediaAsset):
                    logger.error("Provider '%s' returned invalid asset type: %s", provider.name, type(asset))
                    continue
                
                # Provider belirtilmemişse orchestrator'daki provider adını fallback olarak kullan
                safe_provider = asset.provider or provider.name
                unique_key = f"{safe_provider}:{asset.id}"
                
                if unique_key not in seen_keys:
                    seen_keys.add(unique_key)
                    merged_results.append(asset)

        return merged_results
