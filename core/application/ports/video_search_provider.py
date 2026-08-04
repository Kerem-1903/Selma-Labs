from typing import Protocol, Any
from core.domain.entities.media_asset import MediaAsset

class VideoSearchProvider(Protocol):
    """
    Standart Provider Arayüzü (Port). 
    Domain ve Application katmanları sadece bu arayüzü tanır.
    """
    @property
    def name(self) -> str:
        """Provider'ın benzersiz adı (Örn: 'pexels', 'pixabay')"""
        ...
        
    async def search(self, query: str, **kwargs: Any) -> list[MediaAsset]:
        """Arama yapar, hata durumunda exception fırlatır."""
        ...
