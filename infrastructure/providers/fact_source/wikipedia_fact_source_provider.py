from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

from core.domain.exceptions import (
    ProviderConnectionError,
    ProviderError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
)
from core.domain.ports.fact_source_port import FactSourcePort
from core.domain.value_objects.fact_source import FactSource

STOPWORDS = {
    "about",
    "after",
    "before",
    "from",
    "have",
    "into",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "olan",
    "olarak",
    "neden",
    "nasıl",
    "için",
    "sahip",
}


class ParagraphExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "p":
            if self._depth == 0:
                self._parts = []
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag != "p" or self._depth == 0:
            return
        self._depth -= 1
        if self._depth == 0:
            paragraph = " ".join("".join(self._parts).split())
            if paragraph:
                self.paragraphs.append(paragraph)

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._parts.append(data)


class WikipediaFactSourceProvider(FactSourcePort):
    """Retrieves plain-text article introductions through Wikimedia REST APIs."""

    def __init__(
        self,
        language: str = "en",
        timeout_seconds: float = 30.0,
        max_extract_chars: int = 5000,
        fallback_languages: tuple[str, ...] = ("tr",),
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._language = language.strip().lower()
        self._timeout_seconds = timeout_seconds
        self._max_extract_chars = max_extract_chars
        self._fallback_languages = tuple(
            candidate.strip().lower()
            for candidate in fallback_languages
            if candidate.strip() and candidate.strip().lower() != self._language
        )
        self._transport = transport

    @property
    def provider_identity(self) -> str:
        return f"wikipedia:{self._language}"

    async def search(self, topic: str, max_results: int) -> list[FactSource]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
                headers={
                    "User-Agent": "SELMA-Labs/1.0 (source-grounded video fact checking)"
                },
            ) as client:
                sources: list[FactSource] = []
                for language in (self._language, *self._fallback_languages):
                    remaining = max_results - len(sources)
                    if remaining <= 0:
                        break
                    language_sources = await self._search_language(
                        client,
                        topic,
                        remaining,
                        language,
                    )
                    language_sources = self._rank_relevant_sources(
                        language_sources,
                        topic,
                    )
                    known_urls = {source.url for source in sources}
                    sources.extend(
                        source
                        for source in language_sources
                        if source.url not in known_urls
                    )
                    if sources:
                        break
                return sources[:max_results]
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Wikipedia API timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"Could not connect to Wikipedia API: {exc}"
            ) from exc
        except ValueError as exc:
            raise ProviderError("Wikipedia API returned invalid JSON.") from exc

    async def _search_language(
        self,
        client: httpx.AsyncClient,
        topic: str,
        max_results: int,
        language: str,
    ) -> list[FactSource]:
        search_response = await client.get(
            f"https://api.wikimedia.org/core/v1/wikipedia/{language}/search/page",
            params={"q": topic, "limit": max_results},
        )
        self._raise_for_status(search_response)
        search_pages = search_response.json().get("pages", [])
        sources: list[FactSource] = []
        for page in search_pages:
            page_key = str(page.get("key") or "").strip()
            if not page_key:
                continue
            article_response = await client.get(
                (
                    "https://api.wikimedia.org/core/v1/wikipedia/"
                    f"{language}/page/{quote(page_key, safe='')}/with_html"
                )
            )
            if article_response.status_code == 404:
                continue
            self._raise_for_status(article_response)
            article = article_response.json()
            extract = self._extract_relevant_text(
                str(article.get("html") or ""),
                topic,
            )
            title = str(article.get("title") or page.get("title") or "").strip()
            if not title or not extract:
                continue
            source_url = (
                f"https://{language}.wikipedia.org/wiki/"
                f"{quote(page_key, safe='')}"
            )
            sources.append(
                FactSource(
                    title=title,
                    url=source_url,
                    extract=extract[: self._max_extract_chars],
                )
            )
        return sources

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise ProviderQuotaExceededError("Wikipedia API rate limit exceeded.")
        if response.is_error:
            raise ProviderError(
                f"Wikipedia API returned an error (status {response.status_code})."
            )

    @staticmethod
    def _extract_relevant_text(article_html: str, query: str) -> str:
        extractor = ParagraphExtractor()
        extractor.feed(article_html)
        query_tokens = WikipediaFactSourceProvider._tokens(query)
        ranked = sorted(
            extractor.paragraphs,
            key=lambda paragraph: (
                len(query_tokens & WikipediaFactSourceProvider._tokens(paragraph)),
                -len(paragraph),
            ),
            reverse=True,
        )
        relevant = [
            paragraph
            for paragraph in ranked
            if query_tokens & WikipediaFactSourceProvider._tokens(paragraph)
        ]
        return "\n\n".join((relevant or ranked)[:8])

    @staticmethod
    def _tokens(text: str) -> set[str]:
        tokens = set()
        for raw_token in re.findall(r"[^\W\d_]{3,}", text.lower(), flags=re.UNICODE):
            if raw_token in STOPWORDS:
                continue
            if raw_token.endswith("es") and len(raw_token) > 5:
                raw_token = raw_token[:-2]
            elif raw_token.endswith("s") and len(raw_token) > 4:
                raw_token = raw_token[:-1]
            tokens.add(raw_token)
        return tokens

    @classmethod
    def _rank_relevant_sources(
        cls,
        sources: list[FactSource],
        topic: str,
    ) -> list[FactSource]:
        """Remove search-result drift before sending extracts to the LLM.

        Wikimedia search can return pages that share only a generic word such
        as ``heart``.  Prefix matching keeps simple Turkish inflections such as
        ``ahtapot``/``ahtapotların`` together without accepting unrelated pages.
        """
        query_tokens = cls._tokens(topic)
        ranked = sorted(
            sources,
            key=lambda source: cls._topic_relevance_score(
                query_tokens,
                cls._tokens(f"{source.title} {source.extract}"),
            ),
            reverse=True,
        )
        if not ranked:
            return []
        minimum_matches = 2 if len(query_tokens) >= 2 else 1
        relevant = [
            source
            for source in ranked
            if cls._topic_relevance_score(
                query_tokens,
                cls._tokens(f"{source.title} {source.extract}"),
            )
            >= minimum_matches
        ]
        return relevant or ranked[:1]

    @staticmethod
    def _topic_relevance_score(
        query_tokens: set[str],
        source_tokens: set[str],
    ) -> int:
        return sum(
            1
            for query_token in query_tokens
            if any(
                query_token == source_token
                or (
                    min(len(query_token), len(source_token)) >= 5
                    and query_token[:5] == source_token[:5]
                )
                for source_token in source_tokens
            )
        )
