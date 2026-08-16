from __future__ import annotations

import base64
from io import BytesIO
import json
import re

from PIL import Image, UnidentifiedImageError

from core.domain.exceptions import ProviderError
from core.domain.ports.vision_analysis_port import VisionAnalysisPort
from core.domain.value_objects.vision_analysis_result import VisionAnalysisResult
from infrastructure.providers.nvidia.nvidia_chat_client import NvidiaChatClient


class NvidiaVisionProvider(VisionAnalysisPort):
    """Scores candidate frames through an NVIDIA vision model."""

    _EMBEDDED_IMAGE_LIMIT_BYTES = 170 * 1024
    _CONTACT_FRAME_WIDTH = 320
    _RESULT_SCHEMA = {
        "type": "object",
        "properties": {
            "relevance_score": {"type": "number", "minimum": 0, "maximum": 1},
            "scene_type": {"type": "string"},
            "lighting": {"type": "string"},
            "dominant_colors": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
            },
            "indoors": {"type": "boolean"},
            "outdoors": {"type": "boolean"},
            "camera_motion": {"type": "string"},
            "people_present": {"type": "boolean"},
            "vehicles_present": {"type": "boolean"},
            "text_present": {"type": "boolean"},
            "logo_present": {"type": "boolean"},
            "dominant_subject": {"type": "string"},
            "observed_subjects": {"type": "array", "items": {"type": "string"}},
            "observed_actions": {"type": "array", "items": {"type": "string"}},
            "observed_relations": {"type": "array", "items": {"type": "string"}},
            "subject_pose": {"type": "string"},
            "camera_angle": {"type": "string"},
            "background_signature": {"type": "string"},
            "motion_energy": {"type": "number", "minimum": 0, "maximum": 1},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "relevance_score", "scene_type", "lighting", "dominant_colors",
            "indoors", "outdoors", "camera_motion", "people_present",
            "vehicles_present", "text_present", "logo_present", "confidence",
            "dominant_subject", "observed_subjects", "observed_actions",
            "observed_relations", "subject_pose", "camera_angle",
            "background_signature", "motion_energy",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: float = 30.0,
        client: NvidiaChatClient | None = None,
    ) -> None:
        self._client = client or NvidiaChatClient(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
        self._model = model

    @property
    def provider_identity(self) -> str:
        return f"nvidia:{self._model}"

    async def analyze(
        self,
        frame_bytes: list[bytes],
        scene_context: str,
    ) -> VisionAnalysisResult:
        if not frame_bytes:
            raise ProviderError("No frames provided for vision analysis.")
        prompt = (
            "Analyze this contact sheet of sequential video frames, ordered left "
            "to right, for this scene context: "
            f"'{scene_context}'. Return only a JSON object with: relevance_score "
            "(0-1), scene_type, lighting, dominant_colors (maximum 5 items), indoors (bool), "
            "outdoors (bool), camera_motion, people_present (bool), "
            "vehicles_present (bool), text_present (bool), logo_present (bool), "
            "dominant_subject, observed_subjects, observed_actions, observed_relations, "
            "subject_pose, camera_angle, background_signature, motion_energy (0-1), "
            "and judge demonstrated actions/relations rather than subject presence alone; "
            "confidence (0-1)."
        )
        prepared_frame = self._prepare_contact_sheet(frame_bytes)
        encoded = base64.b64encode(prepared_frame).decode("ascii")
        content: list[dict[str, object]] = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
            },
        ]
        raw_text = ""
        parse_error: Exception | None = None
        for response_attempt in range(2):
            raw_text = await self._client.complete(
                model=self._model,
                messages=[{"role": "user", "content": content}],
                max_tokens=1024,
                temperature=0.0,
                extra_body={"nvext": {"guided_json": self._RESULT_SCHEMA}},
            )
            try:
                data = self._parse_response(raw_text)
                break
            except (json.JSONDecodeError, TypeError, ValueError, AttributeError) as exc:
                parse_error = exc
                if response_attempt == 0:
                    content[0] = {
                        "type": "text",
                        "text": (
                            prompt
                            + " This is benign stock-footage quality control. Do not "
                            "refuse; emit exactly the requested fields."
                        ),
                    }
        else:
            preview = raw_text.strip().replace("\n", " ")[:300]
            raise ProviderError(
                f"Invalid NVIDIA vision response: {parse_error}. "
                f"Response preview: {preview}"
            ) from parse_error

        try:
            return VisionAnalysisResult(
                relevance_score=float(data.get("relevance_score", 0.0)),
                scene_type=str(data.get("scene_type", "unknown")),
                lighting=str(data.get("lighting", "unknown")),
                dominant_colors=[str(color) for color in data.get("dominant_colors", [])],
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
        except (TypeError, ValueError, AttributeError) as exc:
            preview = raw_text.strip().replace("\n", " ")[:300]
            raise ProviderError(
                f"Invalid NVIDIA vision response: {exc}. Response preview: {preview}"
            ) from exc

    @classmethod
    def _parse_response(cls, raw_text: str) -> dict[str, object]:
        candidate = cls._extract_json_object(raw_text)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # The hosted Llama Vision endpoint does not consistently honor guided
        # JSON. Parse its stable bold-label fallback instead of discarding an
        # otherwise useful analysis.
        matches = re.findall(
            r"\*\*([^*:]+?):?\*\*\s*:?\s*(.*?)"
            r"(?=(?:\s*\*\s*)?\*\*[^*:]+?:?\*\*\s*:?|$)",
            raw_text,
            flags=re.DOTALL,
        )
        values: dict[str, str] = {}
        for label, value in matches:
            key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
            values[key] = re.sub(r"\s+", " ", value).strip(" -*`.")
        if "relevance_score" not in values:
            raise json.JSONDecodeError("No JSON or labeled score found", raw_text, 0)

        def boolean(key: str) -> bool:
            return values.get(key, "false").lower().split()[0] in {"true", "yes", "1"}

        colors = [
            color.strip(" []'\".")
            for color in re.split(r"[,;/]", values.get("dominant_colors", ""))
            if color.strip(" []'\".")
        ]
        return {
            "relevance_score": cls._first_number(values["relevance_score"]),
            "scene_type": values.get("scene_type", "unknown"),
            "lighting": values.get("lighting", "unknown"),
            "dominant_colors": colors,
            "indoors": boolean("indoors"),
            "outdoors": boolean("outdoors"),
            "camera_motion": values.get("camera_motion", "unknown"),
            "people_present": boolean("people_present"),
            "vehicles_present": boolean("vehicles_present"),
            "text_present": boolean("text_present"),
            "logo_present": boolean("logo_present"),
            "dominant_subject": values.get("dominant_subject", ""),
            "observed_subjects": [
                value.strip() for value in re.split(r"[,;/]", values.get("observed_subjects", ""))
                if value.strip()
            ],
            "observed_actions": [
                value.strip() for value in re.split(r"[,;/]", values.get("observed_actions", ""))
                if value.strip()
            ],
            "observed_relations": [
                value.strip() for value in re.split(r"[,;/]", values.get("observed_relations", ""))
                if value.strip()
            ],
            "subject_pose": values.get("subject_pose", ""),
            "camera_angle": values.get("camera_angle", ""),
            "background_signature": values.get("background_signature", ""),
            "motion_energy": cls._first_number(values.get("motion_energy", "0.5")),
            "confidence": cls._first_number(values.get("confidence", "0.5")),
        }

    @staticmethod
    def _first_number(value: str) -> float:
        match = re.search(r"(?:0(?:\.\d+)?|1(?:\.0+)?)", value)
        if not match:
            raise ValueError(f"No bounded numeric score in {value!r}")
        return float(match.group(0))

    @classmethod
    def _prepare_contact_sheet(cls, frame_bytes: list[bytes]) -> bytes:
        """Return one NVIDIA-compatible JPEG below the embedded-image limit.

        NVIDIA's hosted Llama Vision endpoint accepts at most one image per
        prompt and requires larger images to use its separate asset API.  A
        compact left-to-right contact sheet preserves the temporal samples in
        one request while staying on the OpenAI-compatible endpoint.
        """
        try:
            images = []
            for raw_frame in frame_bytes:
                with Image.open(BytesIO(raw_frame)) as source:
                    frame = source.convert("RGB")
                    width = min(cls._CONTACT_FRAME_WIDTH, frame.width)
                    height = max(1, round(frame.height * width / frame.width))
                    images.append(frame.resize((width, height), Image.Resampling.LANCZOS))
        except (UnidentifiedImageError, OSError, ValueError):
            # Test doubles and custom providers may supply opaque bytes. A
            # single already-small payload remains valid to pass through.
            if len(frame_bytes) == 1 and len(frame_bytes[0]) <= cls._EMBEDDED_IMAGE_LIMIT_BYTES:
                return frame_bytes[0]
            raise ProviderError("NVIDIA vision received an invalid image frame.")

        max_height = max(image.height for image in images)
        sheet = Image.new("RGB", (sum(image.width for image in images), max_height), "black")
        cursor = 0
        for image in images:
            sheet.paste(image, (cursor, (max_height - image.height) // 2))
            cursor += image.width

        for quality in (84, 74, 64, 54, 44):
            buffer = BytesIO()
            sheet.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
            payload = buffer.getvalue()
            if len(payload) <= cls._EMBEDDED_IMAGE_LIMIT_BYTES:
                return payload
        raise ProviderError("NVIDIA vision contact sheet exceeds the embedded-image limit.")

    @staticmethod
    def _extract_json_object(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return cleaned[start : end + 1]
        return cleaned
