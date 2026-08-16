"""Deterministic creative contract checks for narration-ready Shorts scripts."""
from __future__ import annotations

import re
import unicodedata

from core.domain.entities.script import Script
from core.domain.exceptions import NarrativeQualityError
from core.domain.value_objects.narrative_contract import NarrativeBeat, NarrativeContract
from core.domain.value_objects.narrative_quality_report import (
    NarrativeQualityIssue,
    NarrativeQualityReport,
)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_QUESTION_WORDS = {
    "neden": "cause",
    "niçin": "cause",
    "niye": "cause",
    "why": "cause",
    "nasıl": "mechanism",
    "how": "mechanism",
    "what": "definition",
    "ne": "definition",
    "kim": "identity",
    "who": "identity",
    "when": "time",
    "ne zaman": "time",
}
_CAUSAL_MARKERS = (
    "çünkü",
    "bu yüzden",
    "bu nedenle",
    "nedeni",
    "sayesinde",
    "gerektiği için",
    "olduğu için",
    "because",
    "due to",
    "that is why",
    "so that",
    "which allows",
    "which lets",
)
_MECHANISM_MARKERS = (
    "önce",
    "ardından",
    "böylece",
    "yoluyla",
    "aracılığıyla",
    "when",
    "then",
    "by ",
    "through",
    "which",
)
_HOOK_MARKERS = (
    "ama",
    "fakat",
    "oysa",
    "aslında",
    "üç",
    "iki",
    "tek",
    "hiç",
    "sadece",
    "yalnızca",
    "neden",
    "nasıl",
    "biliyor musun",
    "şaşırtıcı",
    "but",
    "yet",
    "actually",
    "only",
    "never",
    "why",
    "how",
    "did you know",
)
_FILLER_PHRASES = (
    "merak uyandırabilir",
    "ilginç bir gerçektir",
    "oldukça ilginçtir",
    "bu ilginç yaratık",
    "bu ilginç konu",
    "yakından bakalım",
    "yakından bakacağız",
    "keşfetmeye çalışalım",
    "keşfedelim",
    "dünyasına dalalım",
    "dünyasına yolculuk",
    "daha fazlasını öğrenelim",
    "şimdi inceleyelim",
    "let's take a closer look",
    "let us take a closer look",
    "let's explore",
    "let us explore",
    "is truly fascinating",
    "is very interesting",
    "you may be surprised",
)
_STOPWORDS = {
    "a", "an", "the", "is", "are", "do", "does", "did", "why", "how", "what",
    "ve", "ile", "bir", "bu", "şu", "mi", "mı", "mu", "mü", "neden", "nasıl",
    "var", "vardır", "için", "olan", "olarak",
}


class NarrativeQualityService:
    """Turns a verified plain script into a measurable narrative artifact."""

    maximum_score = 15
    passing_score = 12

    def evaluate(
        self,
        script: Script,
        *,
        language: str = "und",
    ) -> tuple[Script, NarrativeQualityReport]:
        sentences = self._sentences(script.full_text)
        contract = self._build_contract(script, language)
        answer_index = self._find_answer_index(sentences, contract)
        beats = self._build_beats(sentences, answer_index)
        issues: list[NarrativeQualityIssue] = []

        if len(sentences) < 3:
            issues.append(
                NarrativeQualityIssue(
                    code="insufficient_structure",
                    message="Script needs separate hook, evidence, and payoff beats.",
                    blocking=True,
                )
            )

        hook = sentences[0] if sentences else ""
        if not self._is_strong_hook(hook):
            issues.append(
                NarrativeQualityIssue(
                    code="weak_hook",
                    message=(
                        "Opening is descriptive rather than a precise curiosity, contrast, "
                        "number, question, or consequence hook."
                    ),
                    blocking=True,
                    beat_index=0 if sentences else None,
                )
            )

        if contract.question_to_answer and answer_index is None:
            issues.append(
                NarrativeQualityIssue(
                    code="unanswered_title_question",
                    message=(
                        "The narration does not explicitly satisfy the title's "
                        f"{contract.answer_requirement}."
                    ),
                    blocking=True,
                )
            )

        filler_indexes = [
            index for index, sentence in enumerate(sentences) if self._contains_filler(sentence)
        ]
        for index in filler_indexes:
            issues.append(
                NarrativeQualityIssue(
                    code="filler_sentence",
                    message=f"Beat adds generic invitation or praise instead of information: {sentences[index]}",
                    blocking=True,
                    beat_index=index,
                )
            )

        payoff = sentences[-1] if sentences else ""
        if not payoff or self._contains_filler(payoff) or len(payoff.split()) < 4:
            issues.append(
                NarrativeQualityIssue(
                    code="weak_payoff",
                    message="Closing beat must land the strongest answer or consequence.",
                    blocking=True,
                    beat_index=len(sentences) - 1 if sentences else None,
                )
            )

        if self._has_repeated_sentence(sentences):
            issues.append(
                NarrativeQualityIssue(
                    code="repeated_information",
                    message="The script repeats a sentence-level idea instead of advancing the story.",
                    blocking=False,
                )
            )

        if not 18 <= script.target_duration_seconds <= 25:
            issues.append(
                NarrativeQualityIssue(
                    code="duration_override",
                    message=(
                        f"Single-fact preset prefers 18-25 seconds; explicit target is "
                        f"{script.target_duration_seconds} seconds."
                    ),
                    blocking=False,
                )
            )

        penalty = 0
        codes = {issue.code for issue in issues}
        if "weak_hook" in codes:
            penalty += 4
        if "unanswered_title_question" in codes:
            penalty += 5
        if "insufficient_structure" in codes:
            penalty += 2
        if "filler_sentence" in codes:
            penalty += min(3, len(filler_indexes))
        if "weak_payoff" in codes:
            penalty += 3
        if "repeated_information" in codes:
            penalty += 1
        if "duration_override" in codes:
            penalty += 1
        score = max(0, self.maximum_score - penalty)
        passed = score >= self.passing_score and not any(
            issue.blocking for issue in issues
        )
        report = NarrativeQualityReport(
            contract=contract,
            beats=beats,
            score=score,
            maximum_score=self.maximum_score,
            passed=passed,
            hook_text=hook,
            payoff_text=payoff,
            answer_evidence=(
                sentences[answer_index] if answer_index is not None else None
            ),
            issues=tuple(issues),
        )
        return script.with_narrative(contract, beats), report

    def validate(
        self,
        script: Script,
        *,
        language: str = "und",
    ) -> tuple[Script, NarrativeQualityReport]:
        enriched, report = self.evaluate(script, language=language)
        if not report.passed:
            details = "; ".join(
                f"{issue.code}: {issue.message}" for issue in report.issues if issue.blocking
            )
            raise NarrativeQualityError(
                f"Narrative contract failed ({report.score}/{report.maximum_score}): {details}"
            )
        return enriched, report

    @staticmethod
    def _sentences(text: str) -> list[str]:
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return []
        return [part.strip() for part in _SENTENCE_SPLIT.split(cleaned) if part.strip()]

    def _build_contract(self, script: Script, language: str) -> NarrativeContract:
        topic_normalized = self._normalize(script.topic)
        question_type = next(
            (kind for marker, kind in _QUESTION_WORDS.items() if marker in topic_normalized),
            None,
        )
        is_question = "?" in script.topic or question_type is not None
        answer_requirement = {
            "cause": "cause or necessity with explicit causal language",
            "mechanism": "mechanism or sequence with explicit explanatory language",
            "definition": "definition or identity",
            "identity": "identity",
            "time": "time or sequence",
        }.get(question_type, "central claim with concrete evidence")
        override = None
        if not 18 <= script.target_duration_seconds <= 25:
            override = (
                f"Explicit {script.target_duration_seconds}-second target retained; "
                "creative duration review required."
            )
        return NarrativeContract(
            topic=script.topic,
            language=language or "und",
            target_audience="curious general audience",
            promise=f"Resolve the viewer-facing topic clearly: {script.topic}",
            question_to_answer=script.topic if is_question else None,
            answer_requirement=answer_requirement,
            hook_type="precise curiosity or surprising consequence",
            payoff_requirement="Finish on the strongest answer or consequence, never a generic invitation.",
            target_duration_seconds=script.target_duration_seconds,
            duration_override_reason=override,
        )

    def _find_answer_index(
        self,
        sentences: list[str],
        contract: NarrativeContract,
    ) -> int | None:
        if not contract.question_to_answer:
            return 1 if len(sentences) > 1 else (0 if sentences else None)
        topic = self._normalize(contract.question_to_answer)
        markers = _CAUSAL_MARKERS if any(
            marker in topic for marker in ("neden", "niçin", "niye", "why")
        ) else _MECHANISM_MARKERS if any(
            marker in topic for marker in ("nasıl", "how")
        ) else ()
        if markers:
            for index, sentence in enumerate(sentences):
                normalized = self._normalize(sentence)
                if any(marker in normalized for marker in markers):
                    return index
            return None
        topic_tokens = self._meaningful_tokens(contract.question_to_answer)
        for index, sentence in enumerate(sentences[1:], start=1):
            if len(topic_tokens & self._meaningful_tokens(sentence)) >= min(2, len(topic_tokens)):
                return index
        return None

    def _build_beats(
        self,
        sentences: list[str],
        answer_index: int | None,
    ) -> tuple[NarrativeBeat, ...]:
        beats: list[NarrativeBeat] = []
        last_index = len(sentences) - 1
        for index, sentence in enumerate(sentences):
            if index == 0:
                role = "hook"
                contribution = "opens the viewer promise"
            elif index == last_index:
                role = "payoff"
                contribution = "lands the answer or strongest consequence"
            elif index == 1 and len(sentences) > 3:
                role = "context"
                contribution = "provides minimum context needed for the answer"
            else:
                role = "evidence"
                contribution = "adds concrete evidence or mechanism"
            beats.append(
                NarrativeBeat(
                    index=index,
                    role=role,
                    text=sentence,
                    information_contribution=contribution,
                    contains_answer=index == answer_index,
                )
            )
        return tuple(beats)

    def _is_strong_hook(self, sentence: str) -> bool:
        normalized = self._normalize(sentence)
        return bool(
            sentence
            and (
                "?" in sentence
                or any(marker in normalized for marker in _HOOK_MARKERS)
                or bool(re.search(r"\d", sentence))
            )
            and len(sentence.split()) <= 18
        )

    def _contains_filler(self, sentence: str) -> bool:
        normalized = self._normalize(sentence)
        return any(phrase in normalized for phrase in _FILLER_PHRASES)

    def _has_repeated_sentence(self, sentences: list[str]) -> bool:
        fingerprints: list[set[str]] = []
        for sentence in sentences:
            tokens = self._meaningful_tokens(sentence)
            if len(tokens) < 3:
                continue
            if any(len(tokens & previous) / min(len(tokens), len(previous)) >= 0.8 for previous in fingerprints):
                return True
            fingerprints.append(tokens)
        return False

    @staticmethod
    def _meaningful_tokens(text: str) -> set[str]:
        normalized = NarrativeQualityService._normalize(text)
        return {
            token
            for token in re.findall(r"[a-z0-9çğıöşü]+", normalized)
            if len(token) > 2 and token not in _STOPWORDS
        }

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(
            unicodedata.normalize("NFKC", text or "").casefold().split()
        )

