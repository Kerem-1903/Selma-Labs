import base64
import json
from typing import List
import aiohttp

from core.domain.exceptions import ProviderError
from core.domain.ports.vision_analysis_port import VisionAnalysisPort
from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult


class SelmaGPTVisionProvider(VisionAnalysisPort):
    """Analyzes extracted video frames through local Ollama/SelmaGPT vision models."""

    def __init__(
        self,
        *,
        api_url: str,
        model: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_url.strip():
            raise ProviderError("SelmaGPT API URL is required.")
        if not model.strip():
            raise ProviderError("SelmaGPT vision model must not be empty.")
        self._api_url = api_url
        self._model = model
        self._timeout_seconds = timeout_seconds

    @property
    def provider_identity(self) -> str:
        """Return a cache-safe identifier for the selected model."""
        return f"selmagpt:{self._model}"

    async def analyze(
        self,
        frame_bytes: List[bytes],
        scene_context: str,
    ) -> VisionAnalysisResult:
        """Return structured visual evidence for sequential JPEG frames."""
        if not frame_bytes:
            raise ProviderError("No frames provided for vision analysis.")

        images_b64 = [base64.b64encode(frame).decode('ascii') for frame in frame_bytes]

        prompt = (
            "Analyze these sequential video frames for a Shorts background. "
            f"Target visual intent: '{scene_context}'. "
            "Return ONLY a valid JSON object with the following exact keys: "
            "relevance_score (float 0.0-1.0), scene_type (str), lighting (str), "
            "dominant_colors (list of str), indoors (bool), outdoors (bool), "
            "camera_motion (str), people_present (bool), vehicles_present (bool), "
            "text_present (bool), logo_present (bool), dominant_subject (str), "
            "observed_subjects (list of str), observed_actions (list of str), "
            "observed_relations (list of str), subject_pose (str), camera_angle (str), "
            "background_signature (str), motion_energy (float 0.0-1.0), confidence (float 0.0-1.0). "
            "Do not output markdown blocks or any other text, just the raw JSON."
        )

        payload = {
            "model": self._model,
            "prompt": prompt,
            "images": images_b64,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.1
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self._timeout_seconds)
                ) as response:
                    if response.status != 200:
                        err_text = await response.text()
                        raise ProviderError(f"SelmaGPT returned status {response.status}: {err_text}")
                    result_data = await response.json()

            output_text = result_data.get("response", "")
            return self._to_result(output_text)

        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError(f"SelmaGPT vision error: {error}") from error

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
                raise ValueError("SelmaGPT response must be a JSON object.")

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
            raise ProviderError(f"SelmaGPT vision returned invalid JSON: {error}") from error
