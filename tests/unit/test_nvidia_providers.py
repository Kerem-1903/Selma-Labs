from __future__ import annotations

import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

from core.domain.exceptions import (
    ProviderAuthError,
    ProviderError,
    ProviderQuotaExceededError,
)
from core.domain.entities.script import Script
from core.domain.value_objects.fact_check_report import FactCheckReport, FactClaim
from core.domain.value_objects.fact_source import FactSource
from infrastructure.providers.nvidia.nvidia_chat_client import NvidiaChatClient
from infrastructure.providers.scene_planning.nvidia_scene_planning_provider import (
    NvidiaScenePlanningProvider,
)
from infrastructure.providers.script.nvidia_script_provider import NvidiaScriptProvider
from infrastructure.providers.script.nvidia_fact_grounded_rewriter import (
    NvidiaFactGroundedRewriter,
)
from infrastructure.providers.translation.nvidia_translation_provider import (
    NvidiaTranslationProvider,
)
from infrastructure.providers.vision.nvidia_vision_provider import NvidiaVisionProvider


class FakeChatClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def complete(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return self.response


class SequentialFakeChatClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def complete(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        return self.responses[len(self.calls) - 1]


@pytest.mark.asyncio
async def test_nvidia_chat_client_returns_content_and_bearer_header():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ready"}}]},
        )

    client = NvidiaChatClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    result = await client.complete(
        model="test-model",
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=8,
    )
    assert result == "ready"


@pytest.mark.asyncio
async def test_nvidia_chat_client_merges_provider_specific_body():
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["nvext"]["guided_json"] == {"type": "object"}
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "{}"}}]}
        )

    client = NvidiaChatClient(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )
    result = await client.complete(
        model="test-model",
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=8,
        extra_body={"nvext": {"guided_json": {"type": "object"}}},
    )
    assert result == "{}"


def test_nvidia_chat_client_requires_api_key():
    with pytest.raises(ProviderAuthError):
        NvidiaChatClient(api_key="")


@pytest.mark.asyncio
async def test_nvidia_chat_client_maps_quota_error():
    transport = httpx.MockTransport(lambda request: httpx.Response(429))
    client = NvidiaChatClient(api_key="test-key", transport=transport)
    with pytest.raises(ProviderQuotaExceededError):
        await client.complete(
            model="test-model",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
        )


@pytest.mark.asyncio
async def test_nvidia_chat_client_includes_bounded_error_detail():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(400, text='{"detail":"image is too large"}')
    )
    client = NvidiaChatClient(api_key="test-key", transport=transport)

    with pytest.raises(ProviderError, match="image is too large"):
        await client.complete(
            model="test-model",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
        )


@pytest.mark.asyncio
async def test_nvidia_chat_client_rejects_malformed_response():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    client = NvidiaChatClient(api_key="test-key", transport=transport)
    with pytest.raises(ProviderError, match="invalid chat response"):
        await client.complete(
            model="test-model",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
        )


@pytest.mark.asyncio
async def test_nvidia_chat_client_retries_transient_server_error():
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "recovered"}}]},
        )

    client = NvidiaChatClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
        retry_backoff_seconds=0,
    )
    result = await client.complete(
        model="test-model",
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=8,
    )
    assert result == "recovered"
    assert attempts == 2


@pytest.mark.asyncio
async def test_nvidia_script_provider_builds_script():
    fake_client = FakeChatClient("one two three")
    provider = NvidiaScriptProvider(
        api_key="test-key",
        model="text-model",
        client=fake_client,
    )
    script = await provider.generate_script("Test topic", 15)
    assert script.full_text == "one two three"
    assert script.provider_used == "nvidia:text-model"


@pytest.mark.asyncio
async def test_nvidia_fact_grounded_rewriter_builds_replacement_script():
    fake_client = FakeChatClient("one two three four five six seven eight nine ten " * 2)
    provider = NvidiaFactGroundedRewriter(
        api_key="test-key",
        model="text-model",
        client=fake_client,
    )
    script = Script.create(
        topic="Kangaroo development",
        full_text="An unsupported claim.",
        target_duration_seconds=15,
        provider_used="fake",
    )
    source = FactSource("Kangaroo", "https://example.test", "A joey uses a pouch.")
    report = FactCheckReport.create(
        claims=[FactClaim("Unsupported", "uncertain", "Missing", [], "")],
        sources=[source],
        provider_used="fake:checker",
    )

    rewritten = await provider.rewrite(script, report)

    assert rewritten.topic == script.topic
    assert rewritten.provider_used == "nvidia:text-model:fact-grounded-rewrite"
    assert "Allowed source extracts" in fake_client.calls[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_nvidia_fact_grounded_rewriter_retries_wrong_length():
    fake_client = SequentialFakeChatClient(
        [
            "too short",
            "one two three four five six seven eight nine ten eleven twelve "
            "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty",
        ]
    )
    provider = NvidiaFactGroundedRewriter(
        api_key="test-key",
        model="text-model",
        client=fake_client,
    )
    script = Script.create(
        topic="Kangaroo development",
        full_text="An unsupported claim.",
        target_duration_seconds=15,
        provider_used="fake",
    )
    report = FactCheckReport.create(
        claims=[FactClaim("Unsupported", "uncertain", "Missing", [], "")],
        sources=[FactSource("Kangaroo", "https://example.test", "A joey uses a pouch.")],
        provider_used="fake:checker",
    )

    rewritten = await provider.rewrite(script, report)

    assert rewritten.estimated_word_count == 20
    assert len(fake_client.calls) == 2


@pytest.mark.asyncio
async def test_nvidia_fact_grounded_rewriter_retries_failed_narrative_contract():
    fake_client = SequentialFakeChatClient(
        [
            (
                "Ahtapotlar kapalı dolaşım sistemine sahiptir. Üç kalpleri vardır. "
                "İki kalp solungaçlara, biri vücuda hizmet eder."
            ),
            (
                "Ahtapotun neden üç kalbi var? Çünkü iki kalp kanı solungaçlardan "
                "geçirirken üçüncü kalp vücutta dolaştırır. Bu iş bölümü, oksijenin "
                "vücuda taşınmasını sürdürür."
            ),
        ]
    )
    provider = NvidiaFactGroundedRewriter(
        api_key="test-key",
        model="text-model",
        client=fake_client,
    )
    script = Script.create(
        topic="Ahtapotların neden üç kalbi var?",
        full_text="Desteklenmeyen ilk taslak metni burada bulunuyor.",
        target_duration_seconds=18,
        provider_used="fake",
    )
    report = FactCheckReport.create(
        claims=[FactClaim("Unsupported", "uncertain", "Missing", [], "")],
        sources=[
            FactSource(
                "Ahtapot",
                "https://example.test",
                "İki solungaç kalbi kanı solungaçlardan geçirir; sistemik kalp vücutta dolaştırır.",
            )
        ],
        provider_used="fake:checker",
    )

    rewritten = await provider.rewrite(script, report)

    assert rewritten.full_text.startswith("Ahtapotun neden üç kalbi var?")
    assert len(fake_client.calls) == 2
    repair_prompt = fake_client.calls[1]["messages"][-1]["content"]
    assert "weak_hook" in repair_prompt
    assert "unanswered_title_question" in repair_prompt


@pytest.mark.asyncio
async def test_nvidia_scene_provider_parses_scene_json():
    response = json.dumps(
        [
            {
                "narration": "A rocket launches.",
                "search_keywords": ["rocket launch"],
                "detected_objects": ["rocket"],
                "visual_priority": "high",
            }
        ]
    )
    provider = NvidiaScenePlanningProvider(
        api_key="test-key",
        model="text-model",
        client=FakeChatClient(response),
    )
    scenes = await provider.plan_scenes("A rocket launches.")
    assert scenes[0].search_keywords == ["rocket launch"]
    assert provider.provider_identity == "nvidia:text-model"


@pytest.mark.asyncio
async def test_nvidia_translation_provider_preserves_order():
    provider = NvidiaTranslationProvider(
        api_key="test-key",
        model="text-model",
        client=FakeChatClient('{"translations": ["Merhaba", "Dünya"]}'),
    )
    assert await provider.translate_texts(["Hello", "World"], "Turkish") == [
        "Merhaba",
        "Dünya",
    ]


@pytest.mark.asyncio
async def test_nvidia_translation_provider_batches_large_requests():
    client = SequentialFakeChatClient([
        '{"translations": ["one", "two"]}',
        '{"translations": ["three"]}',
    ])
    provider = NvidiaTranslationProvider(
        api_key="test-key",
        model="text-model",
        client=client,
        max_batch_size=2,
    )

    assert await provider.translate_texts(["bir", "iki", "üç"], "English") == [
        "one", "two", "three"
    ]
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_nvidia_translation_provider_retries_invalid_structure():
    client = SequentialFakeChatClient([
        '{"translations": ["only one"]}',
        '{"translations": ["one", "two"]}',
    ])
    provider = NvidiaTranslationProvider(
        api_key="test-key",
        model="text-model",
        client=client,
        structure_max_retries=1,
    )

    assert await provider.translate_texts(["bir", "iki"], "English") == [
        "one", "two"
    ]
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_nvidia_vision_provider_parses_result():
    response = json.dumps(
        {
            "relevance_score": 0.9,
            "scene_type": "launch",
            "lighting": "daylight",
            "dominant_colors": ["blue"],
            "indoors": False,
            "outdoors": True,
            "camera_motion": "static",
            "people_present": False,
            "vehicles_present": True,
            "confidence": 0.8,
        }
    )
    fake_client = FakeChatClient(response)
    provider = NvidiaVisionProvider(
        api_key="test-key",
        model="vision-model",
        client=fake_client,
    )
    result = await provider.analyze([b"jpeg"], "rocket launch")
    assert result.relevance_score == 0.9
    assert result.vehicles_present is True
    content = fake_client.calls[0]["messages"]
    assert "data:image/jpeg;base64," in str(content)
    assert "guided_json" in str(fake_client.calls[0]["extra_body"])


@pytest.mark.asyncio
async def test_nvidia_vision_provider_sends_multiple_frames_as_one_contact_sheet():
    buffer = BytesIO()
    Image.new("RGB", (1080, 1920), "blue").save(buffer, format="JPEG", quality=95)
    response = json.dumps(
        {
            "relevance_score": 0.9,
            "scene_type": "underwater",
            "lighting": "natural",
            "dominant_colors": ["blue"],
            "indoors": False,
            "outdoors": True,
            "camera_motion": "slow",
            "people_present": False,
            "vehicles_present": False,
            "confidence": 0.8,
        }
    )
    fake_client = FakeChatClient(response)
    provider = NvidiaVisionProvider(
        api_key="test-key", model="vision-model", client=fake_client
    )

    await provider.analyze([buffer.getvalue()] * 3, "octopus underwater")

    content = fake_client.calls[0]["messages"][0]["content"]
    images = [item for item in content if item["type"] == "image_url"]
    assert len(images) == 1
    encoded = images[0]["image_url"]["url"].split(",", 1)[1]
    import base64

    assert len(base64.b64decode(encoded)) <= 170 * 1024


@pytest.mark.asyncio
async def test_nvidia_vision_provider_accepts_json_surrounded_by_prose():
    response = "Result follows:\n" + json.dumps(
        {
            "relevance_score": 0.5,
            "scene_type": "solid color",
            "lighting": "neutral",
            "dominant_colors": ["blue"],
            "indoors": False,
            "outdoors": False,
            "camera_motion": "static",
            "people_present": False,
            "vehicles_present": False,
            "confidence": 0.8,
        }
    ) + "\nEnd of result."
    provider = NvidiaVisionProvider(
        api_key="test-key",
        model="vision-model",
        client=FakeChatClient(response),
    )
    result = await provider.analyze([b"jpeg"], "blue background")
    assert result.scene_type == "solid color"


@pytest.mark.asyncio
async def test_nvidia_vision_provider_accepts_labeled_markdown_fallback():
    response = """
    * **Relevance Score:** 0.91
    * **Scene Type:** Underwater wildlife
    * **Lighting:** Natural
    * **Dominant Colors:** blue, green
    * **Indoors:** false
    * **Outdoors:** true
    * **Camera Motion:** slow tracking
    * **People Present:** false
    * **Vehicles Present:** false
    * **Confidence:** 0.86
    """
    provider = NvidiaVisionProvider(
        api_key="test-key", model="vision-model", client=FakeChatClient(response)
    )

    result = await provider.analyze([b"jpeg"], "octopus underwater")

    assert result.relevance_score == 0.91
    assert result.scene_type == "Underwater wildlife"
    assert result.dominant_colors == ["blue", "green"]
    assert result.outdoors is True


@pytest.mark.asyncio
async def test_nvidia_vision_provider_retries_one_unstructured_refusal():
    valid = json.dumps(
        {
            "relevance_score": 0.81,
            "scene_type": "underwater",
            "lighting": "natural",
            "dominant_colors": ["blue"],
            "indoors": False,
            "outdoors": True,
            "camera_motion": "slow",
            "people_present": False,
            "vehicles_present": False,
            "confidence": 0.84,
        }
    )
    client = SequentialFakeChatClient(["I cannot engage with this topic.", valid])
    provider = NvidiaVisionProvider(
        api_key="test-key", model="vision-model", client=client
    )

    result = await provider.analyze([b"jpeg"], "octopus underwater")

    assert result.relevance_score == 0.81
    assert len(client.calls) == 2
    assert "benign stock-footage" in str(client.calls[1]["messages"])
