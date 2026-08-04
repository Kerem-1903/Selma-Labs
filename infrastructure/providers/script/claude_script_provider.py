"""
ClaudeScriptProvider — concrete ScriptGeneratorPort adapter backed by the
Anthropic API.

This is the ONLY file in the codebase that knows the Anthropic SDK exists.
ScriptService and everything above it depends on ScriptGeneratorPort, never
on this class directly — it is constructed once, in the composition point
(scripts/generate_script_test.py for now, a DI container in a later sprint)
and injected.
"""
from __future__ import annotations

from anthropic import (
    AsyncAnthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
)

from core.domain.entities.script import Script
from core.domain.exceptions import (
    ProviderAuthError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
)
from core.domain.ports.script_generator_port import ScriptGeneratorPort

SYSTEM_PROMPT = """You write narration scripts for short-form vertical video \
(YouTube Shorts, 15-90 seconds spoken).

BEFORE WRITING, silently plan (do not print this plan — only the final narration \
is returned):
1. A hook that opens an unresolved question or surprising claim in the first \
sentence — something the viewer needs the next sentence to resolve.
2. A sequence of concrete visual beats that develop and eventually resolve that \
hook. Each beat is one filmable thing: a specific person, place, object, action, \
or moment in time — never an abstract idea on its own.
3. A closing line that resolves the hook with a satisfying payoff, optionally a \
small final twist. No "part 2" teases, no trailing off.

WRITING RULES:
- Output ONLY the final narration text, meant to be read aloud by a \
text-to-speech voice. Never print your plan, an outline, or labels — narration only.
- Each sentence should correspond to one concrete visual beat from your plan. \
Prefer "a Roman soldier abandoning his post at the frontier" over "military decline \
occurred" — the former is filmable and searchable as stock footage, the latter is not. \
Some genuinely abstract sentences are fine sparingly (e.g. a turning-point statement), \
but the narration as a whole should read as a sequence of concrete, visualizable moments.
- No stage directions, no scene labels, no markdown formatting, no emojis.
- No preamble such as "Here's a script" or "Sure!" — start directly with the narration.
- Base all claims on well-established, verifiable facts. Do not invent statistics, \
quotes, or dates. If a topic is genuinely uncertain or disputed, say so briefly \
rather than presenting a guess as fact.
- Keep sentences short and singular in focus — one visual idea per sentence. This \
also makes the script easier to split into video scenes later.
- Write for a general audience: clear, concrete, no jargon unless immediately explained.
"""

WORDS_PER_MINUTE_TARGET = 150  # used only to phrase the prompt's word-count guidance


class ClaudeScriptProvider(ScriptGeneratorPort):
    """Generates narration scripts using the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ProviderAuthError(
                "Anthropic API key is missing. Set ANTHROPIC_API_KEY in your .env file."
            )
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def generate_script(self, topic: str, target_duration_seconds: int) -> Script:
        prompt = self._build_prompt(topic, target_duration_seconds)

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
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

        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        return Script.create(
            topic=topic,
            full_text=text,
            target_duration_seconds=target_duration_seconds,
            provider_used=f"anthropic:{self._model}",
        )

    @staticmethod
    def _build_prompt(topic: str, target_duration_seconds: int) -> str:
        words_target = int((target_duration_seconds / 60) * WORDS_PER_MINUTE_TARGET)
        return (
            f"Topic: {topic}\n"
            f"Target spoken duration: {target_duration_seconds} seconds "
            f"(approximately {words_target} words at a natural narration pace).\n"
            "Write the narration script now."
        )
