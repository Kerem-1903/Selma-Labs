import aiohttp
import logging
from core.domain.ports.script_generator_port import ScriptGeneratorPort
from core.domain.entities.script import Script
from core.domain.exceptions import ProviderError

logger = logging.getLogger(__name__)

class AgentSwarmScriptProvider(ScriptGeneratorPort):
    """
    Implements a multi-agent swarm architecture for script generation.
    - Writer Agent: Creates the initial draft.
    - Fact-Checker Agent: Reviews and corrects claims.
    - Hook Expert Agent: Rewrites the first sentence to maximize retention.
    - Director Agent: Finalizes the pacing and tone.
    """
    def __init__(self, api_url: str = "http://localhost:11434/api/generate", model: str = "llama3.1:8b"):
        self.api_url = api_url
        self.model = model

    async def _ask_agent(self, role: str, prompt: str) -> str:
        logger.info(f"Agent [{role}] is thinking...")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": f"You are a highly skilled {role} in a professional AI Video Production Studio. Only output the raw script text result. No conversational filler.",
            "stream": False
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=90) as response:
                    if response.status != 200:
                        raise ProviderError(f"{role} failed with status {response.status}")
                    data = await response.json()
                    return data.get("response", "").strip()
        except Exception as e:
            logger.error(f"Agent [{role}] error: {e}")
            raise ProviderError(f"Agent [{role}] failed: {e}")

    async def generate_script(
        self,
        topic: str,
        target_duration_seconds: int,
        language: str | None = None,
    ) -> Script:
        language_instruction = f" Write it in {language}." if language else " Write it in English."

        # 1. Writer Agent
        writer_prompt = (
            f"Write a {target_duration_seconds}-second engaging YouTube Shorts script about: '{topic}'.\n"
            f"Only output the raw spoken narration text. No stage directions, no quotes.{language_instruction}"
        )
        draft = await self._ask_agent("Writer", writer_prompt)

        # 2. Fact-Checker Agent
        checker_prompt = (
            f"Review the following script for factual accuracy. If there are errors, fix them. If it is accurate, keep it exactly as is.\n\nSCRIPT:\n{draft}"
        )
        checked_draft = await self._ask_agent("Fact-Checker", checker_prompt)

        # 3. Hook Expert Agent
        hook_prompt = (
            f"Rewrite ONLY the very first sentence of this script to make it a viral, curiosity-inducing hook. Output ONLY the new first sentence.\n\nSCRIPT:\n{checked_draft}"
        )
        hook = await self._ask_agent("Hook Expert", hook_prompt)

        # Assemble
        # Try to replace the first sentence. A simple heuristic is to replace everything up to the first punctuation.
        # But to be safe, Director will do it.

        # 4. Director Agent
        director_prompt = (
            f"Assemble the final script. Use this new hook: '{hook}'.\n"
            f"Replace the beginning of the old script with the new hook, ensure the tone is energetic, and the length fits {target_duration_seconds} seconds.\n"
            f"OLD SCRIPT:\n{checked_draft}\n\n"
            f"Only output the final raw spoken narration text. No stage directions, no markdown."
        )
        final_script = await self._ask_agent("Director", director_prompt)

        logger.info("Agent Swarm successfully finalized the script.")

        return Script.create(
            topic=topic,
            full_text=final_script,
            target_duration_seconds=target_duration_seconds,
            provider_used="agent_swarm"
        )
