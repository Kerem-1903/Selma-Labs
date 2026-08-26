import aiohttp
import logging
import json
from typing import List, Optional
from core.domain.ports.scene_planning_port import ScenePlanningPort
from core.domain.value_objects.scene import Scene
from core.domain.exceptions import ProviderError

logger = logging.getLogger(__name__)

class SelmaGPTScenePlanningProvider(ScenePlanningPort):
    """
    Plans scenes using the local SelmaGPT model via an OpenAI-compatible endpoint.
    """
    def __init__(self, api_url: str = "http://localhost:8001/v1/chat/completions", model: str = "SelmaGPT-v1", timeout_seconds: float = 60.0):
        self.api_url = api_url
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def plan_scenes(self, script_text: str, visual_manifest_context: Optional[str] = None) -> List[Scene]:
        logger.info(f"Planning scenes via SelmaGPT...")

        system_prompt = (
            "You are a master cinematic director. Split the provided narration script into a list of exact scenes. "
            "For each scene, provide the exact narration text chunk, visual priority (high/medium/low), mood, "
            "a comma-separated list of visual search keywords, and a comma-separated list of detected objects. "
            "IMPORTANT: Your response MUST be valid JSON matching this schema exactly:\n"
            "[\n"
            "  {\n"
            '    "index": 1,\n'
            '    "narration": "exact text from script",\n'
            '    "visual_priority": "high",\n'
            '    "mood": "mysterious",\n'
            '    "search_keywords": ["keyword1", "keyword2"],\n'
            '    "detected_objects": ["object1", "object2"]\n'
            "  }\n"
            "]\n"
            "Only output the JSON array, nothing else."
        )

        user_content = f"Script to plan:\n\n{script_text}"
        if visual_manifest_context:
            user_content += f"\n\nUse this visual context to influence search keywords if relevant:\n{visual_manifest_context}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.4,
            "max_tokens": 2048
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=self.timeout_seconds) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        logger.error(f"SelmaGPT scene planning error: {err_text}")
                        raise ProviderError(f"SelmaGPT Scene Planning API returned {response.status}")

                    data = await response.json()
                    content = data["choices"][0]["message"]["content"].strip()

                    # Clean up potential markdown formatting from LLM
                    if content.startswith("```json"):
                        content = content.split("```json", 1)[1]
                    if content.startswith("```"):
                        content = content.split("```", 1)[1]
                    if content.endswith("```"):
                        content = content.rsplit("```", 1)[0]
                    content = content.strip()

                    parsed_json = json.loads(content)

                    scenes = []
                    for item in parsed_json:
                        scene = Scene(
                            index=item.get("index", len(scenes) + 1),
                            narration=item.get("narration", ""),
                            search_keywords=item.get("search_keywords", []),
                            detected_objects=item.get("detected_objects", []),
                            location=item.get("location", None),
                            mood=item.get("mood", None),
                            visual_priority=item.get("visual_priority", "medium")
                        )
                        scenes.append(scene)

                    return scenes
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse SelmaGPT JSON response: {e}")
            raise ProviderError("SelmaGPT returned invalid JSON for scene planning.") from e
        except Exception as e:
            logger.error(f"SelmaGPT scene planning failed: {e}")
            raise ProviderError(f"SelmaGPT scene planning failed: {e}") from e
