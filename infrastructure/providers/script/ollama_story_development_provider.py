"""Local structured story writer, dialogue editor, and focused critic via Ollama."""

from __future__ import annotations

import json
from dataclasses import replace

import aiohttp

from core.domain.entities.episode_script import (
    AbilityUse,
    DialogueLine,
    EpisodeScene,
    EpisodeScript,
    EpisodeSequence,
    StoryBrief,
)
from core.domain.exceptions import (
    ProviderConnectionError,
    ProviderError,
    ProviderTimeoutError,
    StoryDevelopmentError,
)
from core.domain.ports.dialogue_generator_port import DialogueGeneratorPort
from core.domain.ports.story_generator_port import StoryGeneratorPort
from core.domain.ports.story_reviewer_port import StoryReviewerPort
from core.domain.value_objects.story_review import (
    ReviewSeverity,
    StoryReviewIssue,
    StoryReviewReport,
)


class OllamaStoryDevelopmentProvider(
    StoryGeneratorPort, DialogueGeneratorPort, StoryReviewerPort
):
    def __init__(
        self,
        *,
        api_url: str = "http://localhost:11434/api/generate",
        model: str = "qwen3:8b",
        reviewer_name: str = "continuity-editor",
        timeout_seconds: float = 180.0,
    ) -> None:
        self._api_url = api_url
        self._model = model
        self._reviewer_name = reviewer_name
        self._timeout_seconds = timeout_seconds

    async def generate_episode(
        self, brief: StoryBrief, creative_direction, world_bible, character_bibles
    ) -> EpisodeScript:
        payload = await self._complete(
            "You are a professional original-anime story architect. Return JSON only. "
            "Never imitate named copyrighted works and obey every supplied canon rule.",
            {
                "task": "Create a production-structured episode draft.",
                "brief": {
                    "logline": brief.logline,
                    "episode_number": brief.episode_number,
                    "target_duration_seconds": brief.target_duration_seconds,
                    "language": brief.language,
                },
                "creative_direction": creative_direction.to_dict(),
                "world_bible": world_bible.to_dict(),
                "characters": [bible.to_dict() for bible in character_bibles],
                "output_schema": self._schema(),
            },
        )
        return EpisodeScript.create(
            title=str(payload["title"]),
            logline=str(payload.get("logline", brief.logline)),
            episode_number=brief.episode_number,
            provider_used=f"ollama:{self._model}",
            sequences=self._parse_sequences(payload),
        )

    async def refine_dialogue(
        self, script: EpisodeScript, character_bibles
    ) -> EpisodeScript:
        payload = await self._complete(
            "You are an anime dialogue editor. Preserve plot, scene IDs, locations, "
            "abilities, and sequence structure. Return JSON only.",
            {
                "task": "Make every voice concise, character-specific, and subtextual.",
                "script": script.to_dict(),
                "characters": [bible.to_dict() for bible in character_bibles],
                "output_schema": self._schema(),
            },
        )
        sequences = self._parse_sequences(payload)
        if self._structure(sequences) != self._structure(script.sequences):
            raise StoryDevelopmentError(
                "Dialogue provider changed locked story structure."
            )
        return replace(script, sequences=sequences)

    async def review(
        self, script: EpisodeScript, creative_direction, world_bible, character_bibles
    ) -> StoryReviewReport:
        payload = await self._complete(
            f"You are the {self._reviewer_name}. Find concrete story defects. "
            "Use BLOCKING only when the script must not advance. Return JSON only.",
            {
                "task": "Review causality, character voice, originality, pacing, and payoff.",
                "script": script.to_dict(),
                "creative_direction": creative_direction.to_dict(),
                "world_bible": world_bible.to_dict(),
                "characters": [bible.to_dict() for bible in character_bibles],
                "output_schema": {
                    "issues": [
                        {
                            "code": "string",
                            "message": "string",
                            "severity": "NOTE|WARNING|BLOCKING",
                            "scene_id": "string|null",
                        }
                    ]
                },
            },
        )
        try:
            issues = tuple(
                StoryReviewIssue(
                    code=str(item["code"]),
                    message=str(item["message"]),
                    severity=ReviewSeverity(str(item["severity"]).upper()),
                    scene_id=str(item["scene_id"]) if item.get("scene_id") else None,
                )
                for item in payload.get("issues", [])
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StoryDevelopmentError(
                "Story reviewer returned invalid issue JSON."
            ) from error
        return StoryReviewReport(self._reviewer_name, issues)

    async def _complete(self, system: str, user_payload: dict) -> dict:
        request = {
            "model": self._model,
            "system": system,
            "prompt": json.dumps(user_payload, ensure_ascii=False),
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.35},
        }
        timeout = aiohttp.ClientTimeout(total=self._timeout_seconds)
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.post(self._api_url, json=request) as response,
            ):
                if response.status != 200:
                    raise ProviderError(
                        f"Ollama story request returned {response.status}."
                    )
                envelope = await response.json()
        except TimeoutError as error:
            raise ProviderTimeoutError("Ollama story request timed out.") from error
        except aiohttp.ClientError as error:
            raise ProviderConnectionError(
                f"Ollama story connection failed: {error}"
            ) from error
        try:
            parsed = json.loads(str(envelope["response"]))
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise StoryDevelopmentError(
                "Ollama returned invalid structured story JSON."
            ) from error
        if not isinstance(parsed, dict):
            raise StoryDevelopmentError("Ollama story response must be a JSON object.")
        return parsed

    @staticmethod
    def _parse_sequences(payload: dict) -> tuple[EpisodeSequence, ...]:
        try:
            return tuple(
                EpisodeSequence(
                    id=str(sequence["id"]),
                    title=str(sequence["title"]),
                    scenes=tuple(
                        EpisodeScene(
                            id=str(scene["id"]),
                            title=str(scene["title"]),
                            location=str(scene["location"]),
                            summary=str(scene["summary"]),
                            characters=tuple(
                                str(value) for value in scene["characters"]
                            ),
                            dialogue=tuple(
                                DialogueLine(str(line["speaker"]), str(line["text"]))
                                for line in scene.get("dialogue", [])
                            ),
                            ability_uses=tuple(
                                AbilityUse(str(use["character"]), str(use["ability"]))
                                for use in scene.get("ability_uses", [])
                            ),
                        )
                        for scene in sequence["scenes"]
                    ),
                )
                for sequence in payload["sequences"]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StoryDevelopmentError(
                "Story provider returned invalid episode JSON."
            ) from error

    @staticmethod
    def _structure(sequences) -> tuple:
        return tuple(
            (
                sequence.id,
                tuple((scene.id, scene.location) for scene in sequence.scenes),
            )
            for sequence in sequences
        )

    @staticmethod
    def _schema() -> dict:
        return {
            "title": "string",
            "logline": "string",
            "sequences": [
                {
                    "id": "string",
                    "title": "string",
                    "scenes": [
                        {
                            "id": "string",
                            "title": "string",
                            "location": "canonical location",
                            "summary": "filmable action",
                            "characters": ["canonical name"],
                            "dialogue": [
                                {"speaker": "canonical name", "text": "string"}
                            ],
                            "ability_uses": [
                                {
                                    "character": "canonical name",
                                    "ability": "canonical ability",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
