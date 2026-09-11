"""Claude adapter for structured Episode Director decisions."""

from __future__ import annotations

import json

from anthropic import APIConnectionError, APIStatusError, APITimeoutError, AsyncAnthropic

from core.domain.exceptions import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
    PreProductionValidationError,
    ScenePlanningError,
)
from core.domain.ports.episode_director_decision_port import EpisodeDirectorDecisionPort
from core.domain.value_objects.episode_director_decision import (
    EpisodeDirectorDecision,
    EpisodeSceneDecision,
)

SYSTEM_PROMPT = """You are an episode director. Return ONLY JSON with this shape:
{"decisions":[{"scene_id":"string","purpose":"string","story_beat":"setup|context|conflict|reveal|reaction|transition|payoff","emotional_intent":"string","character_actions":{"character_id":"observable action"},"pose_preferences":{"character_id":"FRONT_NEUTRAL|THREE_QUARTER_LEFT|PROFILE_LEFT|THREE_QUARTER_RIGHT|BACK_FULL_BODY"},"shot_sizes":["wide|medium|close_up|profile|insert"],"background_direction":"string"}],"rationale":"string"}
Return one decision for each screenplay scene, preserving scene IDs. Keep actions observable and background direction concise."""


class ClaudeEpisodeDirectorProvider(EpisodeDirectorDecisionPort):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ProviderAuthError("Anthropic API key is missing for Episode Director.")
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def provider_identity(self) -> str:
        return f"anthropic:{self._model}"

    async def decide(self, screenplay_text: str) -> EpisodeDirectorDecision:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=3000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": screenplay_text}],
            )
        except APITimeoutError as exc:
            raise ProviderTimeoutError(f"Episode Director provider timed out: {exc}") from exc
        except APIConnectionError as exc:
            raise ProviderConnectionError(f"Episode Director provider connection failed: {exc}") from exc
        except APIStatusError as exc:
            if exc.status_code == 401:
                raise ProviderAuthError(f"Episode Director provider rejected credentials: {exc}") from exc
            if exc.status_code == 429:
                raise ProviderQuotaExceededError(f"Episode Director provider quota exceeded: {exc}") from exc
            raise ProviderError(f"Episode Director provider returned status {exc.status_code}: {exc}") from exc

        raw_text = "".join(block.text for block in response.content if block.type == "text").strip()
        return self._parse_response(raw_text)

    @classmethod
    def _parse_response(cls, raw_text: str) -> EpisodeDirectorDecision:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines.pop()
            cleaned = "\n".join(lines).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ScenePlanningError(f"Episode Director returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("decisions"), list):
            raise ScenePlanningError("Episode Director output must contain a decisions list.")
        decisions: list[EpisodeSceneDecision] = []
        for index, item in enumerate(payload["decisions"]):
            if not isinstance(item, dict):
                raise ScenePlanningError(f"Episode Director decision {index} is not an object.")
            try:
                decisions.append(
                    EpisodeSceneDecision(
                        scene_id=str(item.get("scene_id", "")),
                        purpose=str(item.get("purpose", "")),
                        story_beat=str(item.get("story_beat", "")),
                        emotional_intent=str(item.get("emotional_intent", "")),
                        character_actions={str(k): str(v) for k, v in (item.get("character_actions") or {}).items()},
                        pose_preferences={str(k): str(v) for k, v in (item.get("pose_preferences") or {}).items()},
                        shot_sizes=tuple(str(value) for value in (item.get("shot_sizes") or ())),
                        background_direction=str(item.get("background_direction", "")),
                    )
                )
            except (AttributeError, TypeError, ValueError, PreProductionValidationError) as exc:
                raise ScenePlanningError(f"Episode Director decision {index} is invalid: {exc}") from exc
        try:
            return EpisodeDirectorDecision(tuple(decisions), rationale=str(payload.get("rationale", "")))
        except (ValueError, PreProductionValidationError) as exc:
            raise ScenePlanningError(f"Episode Director decisions are invalid: {exc}") from exc
