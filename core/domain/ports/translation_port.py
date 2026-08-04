from abc import ABC, abstractmethod


class TranslationPort(ABC):
    """
    Abstract Port interface defining subtitle text translation capabilities.
    """

    @abstractmethod
    async def translate_texts(self, texts: list[str], target_language: str) -> list[str]:
        """
        Translates a list of strings into the specified target language.
        Must preserve exact list length and element order.
        """
        pass

    @property
    @abstractmethod
    def provider_identity(self) -> str:
        """Return provider identifier string."""
        pass
