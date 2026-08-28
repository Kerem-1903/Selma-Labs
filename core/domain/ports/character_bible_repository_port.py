from abc import ABC, abstractmethod
from core.domain.entities.character_bible import CharacterBible

class CharacterBibleRepositoryPort(ABC):
    """
    Contract for persisting and retrieving the CharacterBible aggregate root.
    """
    @abstractmethod
    async def save(self, bible: CharacterBible) -> None:
        pass

    @abstractmethod
    async def load(self, character_id: str) -> CharacterBible:
        pass
