"""Provider contract for optional structured Episode Director decisions."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.domain.value_objects.episode_director_decision import EpisodeDirectorDecision


class EpisodeDirectorDecisionPort(ABC):
    """Produces validated, provider-neutral editorial hints from screenplay text."""

    @property
    @abstractmethod
    def provider_identity(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def decide(self, screenplay_text: str) -> EpisodeDirectorDecision:
        """Return semantic scene decisions; timing and asset resolution remain local."""
        raise NotImplementedError
