from __future__ import annotations

import json

import httpx
import pytest

from core.application.services.script_fact_check_service import ScriptFactCheckService
from core.domain.entities.script import Script
from core.domain.exceptions import FactCheckError
from core.domain.ports.fact_check_port import FactCheckPort
from core.domain.ports.fact_source_port import FactSourcePort
from core.domain.ports.script_rewriter_port import ScriptRewriterPort
from core.domain.value_objects.fact_check_report import FactCheckReport, FactClaim
from core.domain.value_objects.fact_source import FactSource
from infrastructure.providers.fact_check.nvidia_fact_check_provider import (
    NvidiaFactCheckProvider,
)
from infrastructure.providers.fact_source.wikipedia_fact_source_provider import (
    WikipediaFactSourceProvider,
)


class FakeSourceProvider(FactSourcePort):
    def __init__(self, sources: list[FactSource]) -> None:
        self.sources = sources

    @property
    def provider_identity(self) -> str:
        return "fake:sources"

    async def search(self, topic: str, max_results: int) -> list[FactSource]:
        return self.sources[:max_results]


class FakeFactCheckProvider(FactCheckPort):
    @property
    def provider_identity(self) -> str:
        return "fake:checker"

    async def verify(
        self,
        *,
        topic: str,
        script_text: str,
        sources: list[FactSource],
    ) -> FactCheckReport:
        return FactCheckReport.create(
            claims=[
                FactClaim(
                    claim=script_text,
                    verdict="supported",
                    explanation=topic,
                    source_urls=[sources[0].url],
                    evidence_quote=sources[0].extract,
                )
            ],
            sources=sources,
            provider_used=self.provider_identity,
        )


class FakeChatClient:
    def __init__(self, response: str) -> None:
        self.response = response

    async def complete(self, **kwargs: object) -> str:
        return self.response


class FakeRewriter(ScriptRewriterPort):
    def __init__(self) -> None:
        self.calls = 0

    async def rewrite(
        self,
        script: Script,
        fact_check_report: FactCheckReport,
    ) -> Script:
        self.calls += 1
        return Script.create(
            topic=script.topic,
            full_text=(
                "Kangaroo babies crawl into the pouch after birth and continue "
                "growing there while receiving milk from their mother for many months."
            ),
            target_duration_seconds=script.target_duration_seconds,
            provider_used="fake:grounded-rewrite",
        )


class RewriteAwareFactCheckProvider(FactCheckPort):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def provider_identity(self) -> str:
        return "fake:rewrite-checker"

    async def verify(
        self,
        *,
        topic: str,
        script_text: str,
        sources: list[FactSource],
    ) -> FactCheckReport:
        self.calls += 1
        passed = "crawl into the pouch" in script_text
        return FactCheckReport.create(
            claims=[
                FactClaim(
                    claim=script_text,
                    verdict="supported" if passed else "uncertain",
                    explanation=topic,
                    source_urls=[sources[0].url] if passed else [],
                    evidence_quote=sources[0].extract if passed else "",
                )
            ],
            sources=sources,
            provider_used=self.provider_identity,
        )


def make_script() -> Script:
    return Script.create(
        topic="Octopus hearts",
        full_text="An octopus has three hearts.",
        target_duration_seconds=15,
        provider_used="fake:script",
    )


def test_fact_check_report_requires_sources_for_every_supported_claim():
    report = FactCheckReport.create(
        claims=[
            FactClaim(
                claim="Claim",
                verdict="supported",
                explanation="Explanation",
                source_urls=[],
                evidence_quote="Evidence",
            )
        ],
        sources=[],
        provider_used="fake",
    )
    assert report.verified is False


def test_evidence_quote_must_include_most_of_the_claim_not_only_the_action():
    source = FactSource(
        "Corvus",
        "https://example.test/corvus",
        "Crows frequently damage crops, strew trash, and transfer disease.",
    )
    assert not NvidiaFactCheckProvider._quote_matches_sources(
        "strew trash",
        [source.url],
        [source],
        claim_text="Crows strew trash.",
    )
    assert NvidiaFactCheckProvider._find_best_evidence_quote(
        "Crows strew trash.",
        [source.url],
        [source],
    ) == source.extract


@pytest.mark.asyncio
async def test_fact_check_service_rejects_missing_sources():
    service = ScriptFactCheckService(
        FakeSourceProvider([]),
        FakeFactCheckProvider(),
    )
    with pytest.raises(FactCheckError, match="No reliable fact-check sources"):
        await service.verify(make_script())


@pytest.mark.asyncio
async def test_fact_check_service_returns_verified_report():
    source = FactSource("Octopus", "https://example.test/octopus", "Three hearts")
    service = ScriptFactCheckService(
        FakeSourceProvider([source]),
        FakeFactCheckProvider(),
    )
    report = await service.verify(make_script())
    assert report.verified is True


@pytest.mark.asyncio
async def test_fact_check_service_rewrites_then_verifies_before_returning():
    source = FactSource(
        "Kangaroo",
        "https://example.test/kangaroo",
        "After birth, the joey crawls into the pouch and receives milk.",
    )
    checker = RewriteAwareFactCheckProvider()
    rewriter = FakeRewriter()
    service = ScriptFactCheckService(FakeSourceProvider([source]), checker)

    rewritten, reports = await service.verify_with_rewrites(
        make_script(),
        rewriter,
        max_rewrites=1,
    )

    assert rewritten.provider_used == "fake:grounded-rewrite"
    assert reports[0].verified is False
    assert reports[1].verified is True
    assert checker.calls == 2
    assert rewriter.calls == 1


@pytest.mark.asyncio
async def test_wikipedia_provider_maps_search_results():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search/page"):
            return httpx.Response(
                200,
                json={"pages": [{"id": 123, "key": "Octopus", "title": "Octopus"}]},
            )
        assert request.url.path.endswith("/page/Octopus/with_html")
        return httpx.Response(
            200,
            json={
                "title": "Octopus",
                "html": (
                    "<html><body><p>An octopus is a cephalopod.</p>"
                    "<p>An octopus has three hearts and blue blood.</p></body></html>"
                ),
            },
        )

    provider = WikipediaFactSourceProvider(
        transport=httpx.MockTransport(handler),
    )
    sources = await provider.search("octopus hearts", 3)
    assert sources[0].title == "Octopus"
    assert sources[0].url.endswith("/wiki/Octopus")
    assert "three hearts" in sources[0].extract


@pytest.mark.asyncio
async def test_wikipedia_provider_falls_back_for_turkish_topic():
    requested_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path.endswith("/en/search/page"):
            return httpx.Response(200, json={"pages": []})
        if request.url.path.endswith("/tr/search/page"):
            return httpx.Response(
                200,
                json={"pages": [{"key": "Ahtapot", "title": "Ahtapot"}]},
            )
        return httpx.Response(
            200,
            json={
                "title": "Ahtapot",
                "html": "<p>Ahtapotların üç kalbi ve mavi kanı vardır.</p>",
            },
        )

    provider = WikipediaFactSourceProvider(
        language="en",
        fallback_languages=("tr",),
        transport=httpx.MockTransport(handler),
    )

    sources = await provider.search("Ahtapotların neden üç kalbi var?", 3)

    assert [source.title for source in sources] == ["Ahtapot"]
    assert sources[0].url.startswith("https://tr.wikipedia.org/")
    assert "/en/search/page" in requested_paths[0]
    assert any("/tr/search/page" in path for path in requested_paths)


def test_wikipedia_source_ranking_removes_generic_search_drift():
    sources = [
        FactSource(
            "Ahtapot",
            "https://tr.wikipedia.org/wiki/Ahtapot",
            "Ahtapotların üç kalbi vardır; iki kalp solungaçlarla ilişkilidir.",
        ),
        FactSource(
            "Hayali karakterler",
            "https://example.test/fiction",
            "Bir karakterin kalbi virüsten oluşur.",
        ),
        FactSource(
            "Yemekler",
            "https://example.test/food",
            "Bu sayfa çeşitli yemek tariflerini listeler.",
        ),
    ]

    ranked = WikipediaFactSourceProvider._rank_relevant_sources(
        sources,
        "Ahtapotların neden üç kalbi vardır?",
    )

    assert [source.title for source in ranked] == ["Ahtapot"]


@pytest.mark.asyncio
async def test_nvidia_fact_checker_blocks_contradicted_claim():
    source = FactSource(
        "Octopus",
        "https://example.test/octopus",
        "Two branchial hearts pump blood through the gills.",
    )
    response = json.dumps(
        {
            "claims": [
                {
                    "claim": "One heart pumps blood to the gills.",
                    "verdict": "contradicted",
                    "explanation": "The source says there are two branchial hearts.",
                    "source_urls": [source.url],
                    "evidence_quote": source.extract,
                }
            ]
        }
    )
    provider = NvidiaFactCheckProvider(
        api_key="test-key",
        model="test-model",
        client=FakeChatClient(response),
        audit_enabled=False,
    )
    report = await provider.verify(
        topic="Octopus hearts",
        script_text="One heart pumps blood to the gills.",
        sources=[source],
    )
    assert report.verified is False
    assert report.claims[0].verdict == "contradicted"


@pytest.mark.asyncio
async def test_nvidia_fact_checker_downgrades_unknown_source_url():
    source = FactSource("Octopus", "https://example.test/octopus", "Three hearts")
    response = json.dumps(
        {
            "claims": [
                {
                    "claim": "An octopus has three hearts.",
                    "verdict": "supported",
                    "explanation": "Supported.",
                    "source_urls": ["https://untrusted.test/invented"],
                    "evidence_quote": source.extract,
                }
            ]
        }
    )
    provider = NvidiaFactCheckProvider(
        api_key="test-key",
        model="test-model",
        client=FakeChatClient(response),
        audit_enabled=False,
    )
    report = await provider.verify(
        topic="Octopus hearts",
        script_text="An octopus has three hearts.",
        sources=[source],
    )
    assert report.verified is False
    assert report.claims[0].verdict == "uncertain"


@pytest.mark.asyncio
async def test_nvidia_fact_checker_requires_second_pass_support():
    source = FactSource(
        "Octopus",
        "https://example.test/octopus",
        "Two gill hearts pump blood through the gills and one main heart serves the body.",
    )

    class SequenceChatClient:
        def __init__(self) -> None:
            self.models: list[str] = []
            self.responses = [
                json.dumps(
                    {
                        "claims": [
                            {
                                "claim": "One heart pumps blood to the gills.",
                                "verdict": "supported",
                                "explanation": "Initial incorrect decision.",
                                "source_urls": [source.url],
                                "evidence_quote": source.extract,
                            }
                        ]
                    }
                ),
                json.dumps(
                    {
                        "audits": [
                            {
                                "index": 0,
                                "verdict": "contradicted",
                                "explanation": "The quantities are reversed.",
                            }
                        ]
                    }
                ),
            ]

        async def complete(self, **kwargs: object) -> str:
            self.models.append(str(kwargs["model"]))
            return self.responses.pop(0)

    client = SequenceChatClient()
    provider = NvidiaFactCheckProvider(
        api_key="test-key",
        model="test-model",
        audit_model="audit-model",
        client=client,
    )
    report = await provider.verify(
        topic="Octopus hearts",
        script_text="One heart pumps blood to the gills.",
        sources=[source],
    )
    assert report.verified is False
    assert report.claims[0].verdict == "contradicted"
    assert client.models == ["test-model", "audit-model"]


def test_evidence_quote_matching_tolerates_articles_and_punctuation():
    source = FactSource(
        "Octopus",
        "https://example.test/octopus",
        "The octopus has three hearts; two serve the gills.",
    )
    assert NvidiaFactCheckProvider._quote_matches_sources(
        "An octopus has three hearts.",
        [source.url],
        [source],
    )


def test_evidence_quote_matching_rejects_changed_quantity():
    source = FactSource(
        "Octopus",
        "https://example.test/octopus",
        "Two hearts pump blood through the gills.",
    )
    assert not NvidiaFactCheckProvider._quote_matches_sources(
        "One heart pumps blood through the gills.",
        [source.url],
        [source],
    )


def test_evidence_quote_matching_preserves_turkish_letters_and_quantities():
    source = FactSource(
        "Ahtapot",
        "https://example.test/octopus",
        "Ahtapotların üç kalbi vardır; iki kalp solungaçlardan kan geçirir.",
    )

    assert NvidiaFactCheckProvider._quote_matches_sources(
        "Ahtapotların üç kalbi vardır.",
        [source.url],
        [source],
        claim_text="Ahtapotların üç kalbi vardır.",
    )
    assert not NvidiaFactCheckProvider._quote_matches_sources(
        "Ahtapotların iki kalbi vardır.",
        [source.url],
        [source],
        claim_text="Ahtapotların iki kalbi vardır.",
    )


def test_evidence_quote_matching_handles_turkish_inflections():
    source = FactSource(
        "Venüs",
        "https://example.test/venus",
        (
            "Dolayısıyla bir Venüs yıldız günü, bir Venüs yılından daha uzundur "
            "(243'e karşı 224,7 Dünya günü)."
        ),
    )

    assert NvidiaFactCheckProvider._quote_matches_sources(
        source.extract,
        [source.url],
        [source],
        claim_text="Venüs'te bir gün bir yıldan uzun.",
    )


def test_best_evidence_quote_fills_missing_model_quote():
    source = FactSource(
        "Octopus",
        "https://example.test/octopus",
        "The octopus has three hearts. Two hearts serve the gills.",
    )
    quote = NvidiaFactCheckProvider._find_best_evidence_quote(
        "An octopus has three hearts.",
        [source.url],
        [source],
    )
    assert quote == "The octopus has three hearts."
