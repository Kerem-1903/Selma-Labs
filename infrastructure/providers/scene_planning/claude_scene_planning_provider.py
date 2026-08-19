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
- Optimize for high-retention Shorts pacing: create a new visual beat roughly \
every 2-3 spoken seconds. A 30-second narration should normally produce 8-12 scenes.
- Split sentences at natural clauses when one sentence contains multiple filmable \
actions or subjects. Do not place an entire narration into one scene.
- Preserve the narration text verbatim inside each scene's "narration" field: \
preserve every word and its original order across the full scene list; do not \
paraphrase, summarize, omit, or duplicate narration.
- Every scene must have 2 to 5 concise search_keywords: short, concrete, \
stock-footage-searchable phrases (e.g. "titanic ship", "harbor departure"), \
never abstract ideas like "human ambition" or "the passage of time".
- generation_prompt: A highly detailed, cinematic prompt for a Text-to-Video AI model (like Kling or Runway). It must describe the subject, lighting, camera movement, and mood specifically (e.g., "A hyper-realistic cinematic tracking shot of the Titanic departing Southampton harbor, golden hour lighting, 8k resolution, photorealistic").
- The JSON output must include "generation_prompt" alongside "search_keywords".
- detected_objects: concrete physical objects or subjects visible in that \
scene (e.g. "ship", "passengers", "iceberg"). Empty list if none are clearly \
implied.
- location: a short concrete place description if the scene clearly implies \
one (e.g. "harbor", "open ocean"), or null if none is implied. Never guess a \
specific real-world location beyond what the narration actually supports.
- mood: one simple word for the emotional tone if the scene has a clear one \
(e.g. "hope", "tension", "tragedy"), or null if neutral or unclear.
- Make adjacent scenes use visibly different search intent: wide shot, close-up, \
specific action, anatomy, environment, or payoff whenever the narration allows it.
- visual_priority: "high" for scenes central to the story's visual impact, \
"medium" for standard supporting scenes, "low" for brief transitional ones.
- visual_job: choose exactly one of "establish_subject", "locate_part", \
"demonstrate_mechanism", "compare_states", "show_consequence", \
"deliver_payoff", or "support_context". This states what the image must teach, \
not merely what subject it contains.
- required_subjects, required_actions, and required_relations: concrete visual \
evidence that must be observable. Subject presence alone is not enough for anatomy, \
mechanism, comparison, or causal claims.
- forbidden_dominant_subjects: objects or species that would make the scene \
misleading even if the environment matches.
- explanatory_required: true for anatomy, internal mechanism, quantities, flows, \
comparisons, or causal relations that ordinary stock footage cannot visibly prove.
- explanation_mode: "stock" only when footage can show the claim; otherwise use \
"overlay", "diagram", or "hybrid".
- overlay_labels: one to three short viewer-facing labels when explanation_mode is \
not stock. Never return explanatory_required=true with an empty label list.

OUTPUT FORMAT:
Return ONLY a JSON array, nothing else — no markdown code fences, no prose, \
no explanation before or after. Each array element must be an object with \
exactly these keys:
{"narration": "...", "search_keywords": ["...", "..."], "detected_objects": \
["...", "..."], "location": "..." or null, "mood": "..." or null, \
"visual_priority": "high" | "medium" | "low", "visual_job": "...", \
"required_subjects": ["..."], "required_actions": ["..."], \
"required_relations": ["..."], "forbidden_dominant_subjects": ["..."], \
"explanation_mode": "stock" | "overlay" | "diagram" | "hybrid", \
"overlay_labels": ["..."], "explanatory_required": true | false}
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
                    visual_job=str(item.get("visual_job") or "support_context"),
                    required_subjects=[
                        str(value) for value in (item.get("required_subjects") or [])
                    ],
                    required_actions=[
                        str(value) for value in (item.get("required_actions") or [])
                    ],
                    required_relations=[
                        str(value) for value in (item.get("required_relations") or [])
                    ],
                    forbidden_dominant_subjects=[
                        str(value)
                        for value in (item.get("forbidden_dominant_subjects") or [])
                    ],
                    explanation_mode=str(item.get("explanation_mode") or "stock"),
                    overlay_labels=[
                        str(value) for value in (item.get("overlay_labels") or [])
                    ],
                    explanatory_required=bool(item.get("explanatory_required", False)),
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
