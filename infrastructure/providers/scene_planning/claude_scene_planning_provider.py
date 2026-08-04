"""
ClaudeScenePlanningProvider — concrete ScenePlanningPort adapter backed by
the Anthropic API.

This is the ONLY file in the codebase that knows how to prompt Claude for
scene planning, or what JSON shape it's expected to return. ScenePlanningService
and everything above it depends on ScenePlanningPort, never on this class
directly — same pattern as ClaudeScriptProvider in Sprint 1.

Design note: this adapter asks Claude for narration grouping, keywords,
objects, location, and mood — but deliberately NOT for timing. See
ScenePlanningPort's docstring for why: an LLM has no reliable sense of
elapsed seconds, so asking it to guess start/end times would just be
inventing precision that isn't there. Timing is computed by
ScenePlanningService from a real measured value instead.
"""
from __future__ import annotations

import json

from anthropic import (
    AsyncAnthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
)

from core.domain.exceptions import (
    ProviderAuthError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
    ScenePlanningError,
)
from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.value_objects.scene import Scene

SYSTEM_PROMPT = """You are a scene planner for short-form vertical video narration \
(YouTube Shorts). Given a full narration script, break it into a sequence of \
logical VISUAL scenes that a later stage will use to search for matching stock \
video footage.

RULES:
- Group related sentences into one scene when they describe the same visual \
moment, idea, or beat. Do NOT create a new scene for every sentence \
mechanically — only start a new scene when the narration genuinely moves to \
a different visual moment, location, or beat.
- Preserve the narration text verbatim inside each scene's "narration" field: \
concatenate the original sentences belonging to that scene, do not paraphrase \
or summarize them.
- Every scene must have 2 to 5 concise search_keywords: short, concrete, \
stock-footage-searchable phrases (e.g. "titanic ship", "harbor departure"), \
never abstract ideas like "human ambition" or "the passage of time".
- detected_objects: concrete physical objects or subjects visible in that \
scene (e.g. "ship", "passengers", "iceberg"). Empty list if none are clearly \
implied.
- location: a short concrete place description if the scene clearly implies \
one (e.g. "harbor", "open ocean"), or null if none is implied. Never guess a \
specific real-world location beyond what the narration actually supports.
- mood: one simple word for the emotional tone if the scene has a clear one \
(e.g. "hope", "tension", "tragedy"), or null if neutral or unclear.
- visual_priority: "high" for scenes central to the story's visual impact, \
"medium" for standard supporting scenes, "low" for brief transitional ones.

OUTPUT FORMAT:
Return ONLY a JSON array, nothing else — no markdown code fences, no prose, \
no explanation before or after. Each array element must be an object with \
exactly these keys:
{"narration": "...", "search_keywords": ["...", "..."], "detected_objects": \
["...", "..."], "location": "..." or null, "mood": "..." or null, \
"visual_priority": "high" | "medium" | "low"}
"""

VALID_PRIORITIES = {"high", "medium", "low"}


class ClaudeScenePlanningProvider(ScenePlanningPort):
    """Plans visual scenes from narration text using the Anthropic Messages
    API."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ProviderAuthError(
                "Anthropic API key is missing. Set ANTHROPIC_API_KEY in your .env file."
            )
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def provider_identity(self) -> str:
        return f"anthropic:{self._model}"

    async def plan_scenes(self, narration_text: str) -> list[Scene]:
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": narration_text}],
            )
        except APITimeoutError as exc:
            raise ProviderTimeoutError(f"Anthropic API timed out: {exc}") from exc
        except APIConnectionError as exc:
            raise ProviderTimeoutError(f"Could not connect to Anthropic API: {exc}") from exc
        except APIStatusError as exc:
            if exc.status_code == 401:
                raise ProviderAuthError(f"Anthropic API rejected the API key: {exc}") from exc
            if exc.status_code == 429:
                raise ProviderQuotaExceededError(
                    f"Anthropic API rate limit or quota exceeded: {exc}"
                ) from exc
            raise ProviderError(
                f"Anthropic API returned an error (status {exc.status_code}): {exc}"
            ) from exc

        raw_text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        return self._parse_response(raw_text)

    @classmethod
    def _parse_response(cls, raw_text: str) -> list[Scene]:
        """Translate Claude's raw JSON text into a list of Scene objects.

        This is the only place in the codebase that reads Claude's scene
        plan response shape. Raises ScenePlanningError (not ProviderError)
        for content problems — the API call itself succeeded, but what
        came back couldn't be turned into scenes.
        """
        cleaned = cls._strip_code_fence(raw_text)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ScenePlanningError(
                f"Claude returned scene plan output that wasn't valid JSON: {exc}"
            ) from exc

        if not isinstance(data, list):
            raise ScenePlanningError(
                "Claude's scene plan output was valid JSON but not a list of scenes."
            )

        scenes: list[Scene] = []
        for position, item in enumerate(data):
            if not isinstance(item, dict) or not item.get("narration"):
                raise ScenePlanningError(
                    f"Scene at position {position} is missing required 'narration' text."
                )
            scenes.append(
                Scene(
                    index=position,
                    narration=str(item["narration"]).strip(),
                    search_keywords=[str(k) for k in (item.get("search_keywords") or [])],
                    detected_objects=[str(o) for o in (item.get("detected_objects") or [])],
                    location=item.get("location") or None,
                    mood=item.get("mood") or None,
                    visual_priority=cls._normalize_priority(item.get("visual_priority")),
                )
            )
        return scenes

    @staticmethod
    def _normalize_priority(value: object) -> str:
        if isinstance(value, str) and value.strip().lower() in VALID_PRIORITIES:
            return value.strip().lower()
        return "medium"

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        text = text.strip()
        if not text.startswith("```"):
            return text
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
