"""OpenAI Responses API adapter for visual-asset analysis."""
from __future__ import annotations

import base64
import json
from typing import Any

from openai import AsyncOpenAI

from core.domain.exceptions import ProviderError
from core.domain.ports.vision_analysis_port import VisionAnalysisPort
from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult


class OpenAIVisionProvider(VisionAnalysisPort):
    """Analyzes extracted video frames through OpenAI's multimodal API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ProviderError("OpenAI API key is required.")
        if not model.strip():
            raise ProviderError("OpenAI vision model must not be empty.")
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

    @property
    def provider_identity(self) -> str:
        """Return a cache-safe identifier for the selected OpenAI model."""
        return f"openai:{self._model}"

    async def analyze(
        self,
        frame_bytes: list[bytes],
        scene_context: str,
    ) -> VisionAnalysisResult:
        """Return structured visual evidence for sequential JPEG frames."""
        if not frame_bytes:
            raise ProviderError("No frames provided for vision analysis.")

        content: list[dict[str, Any]] = [
            {"type": "input_text", "text": self._prompt(scene_context)}
        ]
        content.extend(
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{base64.b64encode(frame).decode('ascii')}",
                "detail": "low",
            }
            for frame in frame_bytes
        )
        try:
            response = await self._client.responses.create(
                model=self._model,
                input=[{"role": "user", "content": content}],
            )
            return self._to_result(response.output_text)
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError(f"OpenAI vision error: {error}") from error

    @staticmethod
    def _prompt(scene_context: str) -> str:
        return (
            "Analyze these sequential video frames for a Shorts background. "
            f"Target visual intent: {scene_context!r}. "
            "Return only a JSON object with relevance_score, scene_type, lighting, "
            "dominant_colors, indoors, outdoors, camera_motion, people_present, "
            "vehicles_present, text_present, logo_present, and confidence. "
            "Also return dominant_subject, observed_subjects, observed_actions, "
            "observed_relations, subject_pose, camera_angle, background_signature, "
            "and motion_energy (0-1). Judge whether the frames demonstrate the requested "
            "action or relation, not only whether they contain the general subject. "
            "Scores and confidence must be between "
            "0.0 and 1.0."
        )

    @staticmethod
    def _to_result(output_text: str) -> VisionAnalysisResult:
        try:
            payload = output_text.strip()
            if payload.startswith("```json"):
                payload = payload[7:]
            if payload.startswith("```"):
                payload = payload[3:]
            if payload.endswith("```"):
                payload = payload[:-3]
            data = json.loads(payload.strip())
            if not isinstance(data, dict):
                raise ValueError("OpenAI response must be a JSON object.")
            return VisionAnalysisResult(
                relevance_score=float(data.get("relevance_score", 0.0)),
                scene_type=str(data.get("scene_type", "unknown")),
                lighting=str(data.get("lighting", "unknown")),
                dominant_colors=[str(value) for value in data.get("dominant_colors", [])],
                indoors=bool(data.get("indoors", False)),
                outdoors=bool(data.get("outdoors", False)),
                camera_motion=str(data.get("camera_motion", "unknown")),
                people_present=bool(data.get("people_present", False)),
                vehicles_present=bool(data.get("vehicles_present", False)),
                confidence=float(data.get("confidence", 0.0)),
                text_present=bool(data.get("text_present", False)),
                logo_present=bool(data.get("logo_present", False)),
                dominant_subject=str(data.get("dominant_subject", "")),
                observed_subjects=[str(value) for value in data.get("observed_subjects", [])],
                observed_actions=[str(value) for value in data.get("observed_actions", [])],
                observed_relations=[str(value) for value in data.get("observed_relations", [])],
                subject_pose=str(data.get("subject_pose", "")),
                camera_angle=str(data.get("camera_angle", "")),
                background_signature=str(data.get("background_signature", "")),
                motion_energy=(
                    float(data["motion_energy"])
                    if data.get("motion_energy") is not None
                    else None
                ),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProviderError(f"OpenAI vision returned invalid JSON: {error}") from error
