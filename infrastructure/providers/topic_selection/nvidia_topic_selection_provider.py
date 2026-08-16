from __future__ import annotations

import json

from core.domain.exceptions import TrendDiscoveryError
from core.domain.ports.topic_selection_port import TopicSelectionPort
from core.domain.value_objects.trend_topic_selection import TrendTopicSelection
from core.domain.value_objects.trend_video import TrendVideo
from infrastructure.providers.nvidia.nvidia_chat_client import NvidiaChatClient

SYSTEM_PROMPT = """You select original topics for an educational YouTube Shorts
channel focused on science, nature, and animals. Analyze the supplied popular
short-form videos as demand signals, not as scripts to copy.

Return only JSON with topic, angle, rationale, and source_video_ids.
- topic: one concise factual question or subject in the requested language
- angle: the specific curiosity gap for a 15-60 second video
- rationale: why the trend signals support this choice
- source_video_ids: 1-5 IDs from the supplied candidates

Do not copy a candidate title verbatim. Avoid celebrity news, politics, medical
advice, dangerous challenges, and claims that cannot be checked against reliable
reference sources. Prefer broad, stable natural phenomena, animal anatomy, and
well-established behavior with a clear encyclopedia article and searchable stock
footage. Reject one-off viral events, branded inventions, demonstrations, training
programs, or human interventions when the candidate description provides no
reliable supporting detail. A popular but unverifiable candidate must not win."""

AUDIT_PROMPT = """Audit whether each proposed source video is directly relevant
to the selected topic and angle. Keep a video only when its title or description
is about the same subject or phenomenon. General popularity, broad science themes,
or unrelated animals are not sufficient. Return only JSON with one key named
relevant_source_video_ids containing IDs from the supplied source videos."""


class NvidiaTopicSelectionProvider(TopicSelectionPort):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout_seconds: float = 180.0,
        client: NvidiaChatClient | None = None,
        audit_model: str | None = None,
        audit_enabled: bool = True,
    ) -> None:
        self._client = client or NvidiaChatClient(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
        self._model = model
        self._audit_model = audit_model or model
        self._audit_enabled = audit_enabled

    @property
    def provider_identity(self) -> str:
        return f"nvidia:{self._model}"

    async def select(
        self,
        *,
        candidates: list[TrendVideo],
        language: str,
    ) -> TrendTopicSelection:
        payload = [candidate.to_dict() for candidate in candidates]
        raw_text = await self._client.complete(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Output language: {language}\n"
                        f"Candidates:\n{json.dumps(payload, ensure_ascii=False)}"
                    ),
                },
            ],
            max_tokens=700,
            temperature=0.2,
        )
        try:
            data = json.loads(self._extract_json_object(raw_text))
        except json.JSONDecodeError as exc:
            raise TrendDiscoveryError(
                f"Invalid NVIDIA topic-selection response: {exc}"
            ) from exc
        topic = str(data.get("topic") or "").strip()
        angle = str(data.get("angle") or "").strip()
        rationale = str(data.get("rationale") or "").strip()
        valid_ids = {candidate.video_id for candidate in candidates}
        source_video_ids = [
            str(video_id)
            for video_id in (data.get("source_video_ids") or [])
            if str(video_id) in valid_ids
        ]
        if not topic or not angle or not rationale or not source_video_ids:
            raise TrendDiscoveryError(
                "NVIDIA topic selection omitted required topic evidence."
            )
        if any(topic.casefold() == candidate.title.casefold() for candidate in candidates):
            raise TrendDiscoveryError(
                "NVIDIA copied a source video title instead of creating an original topic."
            )
        if self._audit_enabled:
            source_video_ids = await self._audit_sources(
                topic=topic,
                angle=angle,
                source_video_ids=source_video_ids,
                candidates=candidates,
            )
        if not source_video_ids:
            raise TrendDiscoveryError(
                "No source trend video directly supports the selected topic."
            )
        return TrendTopicSelection(
            topic=topic,
            angle=angle,
            rationale=rationale,
            source_video_ids=source_video_ids,
            candidates=candidates,
            provider_used=self.provider_identity,
        )

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

    async def _audit_sources(
        self,
        *,
        topic: str,
        angle: str,
        source_video_ids: list[str],
        candidates: list[TrendVideo],
    ) -> list[str]:
        source_id_set = set(source_video_ids)
        source_videos = [
            {
                "video_id": candidate.video_id,
                "title": candidate.title,
                "description": candidate.description,
            }
            for candidate in candidates
            if candidate.video_id in source_id_set
        ]
        raw_text = await self._client.complete(
            model=self._audit_model,
            messages=[
                {"role": "system", "content": AUDIT_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "topic": topic,
                            "angle": angle,
                            "source_videos": source_videos,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            max_tokens=500,
            temperature=0.0,
        )
        try:
            data = json.loads(self._extract_json_object(raw_text))
        except json.JSONDecodeError as exc:
            raise TrendDiscoveryError(
                f"Invalid NVIDIA topic-source audit response: {exc}"
            ) from exc
        return [
            str(video_id)
            for video_id in (data.get("relevant_source_video_ids") or [])
            if str(video_id) in source_id_set
        ]
