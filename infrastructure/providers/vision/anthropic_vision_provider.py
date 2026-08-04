import base64
import json
from typing import List

import anthropic

from core.domain.exceptions import ProviderError
from core.domain.ports.vision_analysis_port import VisionAnalysisPort
from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult


class AnthropicVisionProvider(VisionAnalysisPort):
    def __init__(
        self,
        api_key: str,
        model_name: str = "claude-3-5-sonnet-20241022",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key:
            raise ProviderError("Anthropic API key is required.")
        self._model_name = model_name
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)

    @property
    def provider_identity(self) -> str:
        return f"anthropic:{self._model_name}"

    async def analyze(self, frame_bytes: List[bytes], scene_context: str) -> VisionAnalysisResult:
        if not frame_bytes:
            raise ProviderError("No frames provided for vision analysis.")

        content = []
        for fb in frame_bytes:
            b64 = base64.b64encode(fb).decode("utf-8")
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
            })

        prompt = (
            f"Analyze these sequential frames from a video candidate for the following scene:\n"
            f"Scene Context: '{scene_context}'\n\n"
            f"Return ONLY a JSON object exactly matching this structure:\n"
            f"{{\n"
            f"  \"relevance_score\": float (0.0 to 1.0),\n"
            f"  \"scene_type\": str,\n"
            f"  \"lighting\": str,\n"
            f"  \"dominant_colors\": list of str,\n"
            f"  \"indoors\": bool,\n"
            f"  \"outdoors\": bool,\n"
            f"  \"camera_motion\": str,\n"
            f"  \"people_present\": bool,\n"
            f"  \"vehicles_present\": bool,\n"
            f"  \"confidence\": float (0.0 to 1.0)\n"
            f"}}\n"
        )
        content.append({"type": "text", "text": prompt})

        try:
            response = await self._client.messages.create(
                model=self._model_name,
                max_tokens=1024,
                messages=[{"role": "user", "content": content}],
            )
            text = response.content[0].text

            if text.startswith("```json"): text = text[7:]
            if text.startswith("```"): text = text[3:]
            if text.endswith("```"): text = text[:-3]

            data = json.loads(text.strip())
            return VisionAnalysisResult(
                relevance_score=float(data.get("relevance_score", 0.0)),
                scene_type=str(data.get("scene_type", "unknown")),
                lighting=str(data.get("lighting", "unknown")),
                dominant_colors=list(data.get("dominant_colors", [])),
                indoors=bool(data.get("indoors", False)),
                outdoors=bool(data.get("outdoors", False)),
                camera_motion=str(data.get("camera_motion", "unknown")),
                people_present=bool(data.get("people_present", False)),
                vehicles_present=bool(data.get("vehicles_present", False)),
                confidence=float(data.get("confidence", 0.0)),
            )

        except Exception as e:
            raise ProviderError(f"Anthropic vision error: {e}") from e
